"""
This code was taken and slightly modified from the PyDev.Debugger project which is under the Eclipse Public License 1.0
https://github.com/fabioz/PyDev.Debugger/blob/main/_pydevd_bundle/pydevd_reload.py.

Based on the python xreload.

Changes
======================

1. we don't recreate the old namespace from new classes. Rather, we keep the existing namespace,
load a new version of it and update only some of the things we can inplace. That way, we don't break
things such as singletons or end up with a second representation of the same class in memory.

2. If we find it to be a __metaclass__, we try to update it as a regular class.

3. We don't remove old attributes (and leave them lying around even if they're no longer used).

4. Reload hooks were changed

These changes make it more stable, especially in the common case (where in a debug session only the
contents of a function are changed), besides providing flexibility for users that want to extend
on it.



Hooks
======================

Classes/modules can be specially crafted to work with the reload (so that it can, for instance,
update some constant which was changed).

1. To participate in the change of some attribute:

    In a module:

    __xreload_old_new__(namespace, name, old, new)

    in a class:

    @classmethod
    __xreload_old_new__(cls, name, old, new)

    A class or module may include a method called '__xreload_old_new__' which is called when we're
    unable to reload a given attribute.



2. To do something after the whole reload is finished:

    In a module:

    __xreload_after_reload_update__(namespace):

    In a class:

    @classmethod
    __xreload_after_reload_update__(cls):


    A class or module may include a method called '__xreload_after_reload_update__' which is called
    after the reload finishes.


Important: when providing a hook, always use the namespace or cls provided and not anything in the global
namespace, as the global namespace are only temporarily created during the reload and may not reflect the
actual application state (while the cls and namespace passed are).


Current limitations
======================


- Attributes/constants are added, but not changed (so singletons and the application state is not
  broken -- use provided hooks to workaround it).

- Code using metaclasses may not always work.

- Decorated functions are updated when the decorator uses functools.wraps, keeps the function in its
  closure or wraps it in an object with __wrapped__ (e.g. functools.lru_cache, whose cache is cleared).
  Properties, classmethods and staticmethods are updated in place.

- Functions whose closure variables changed cannot be updated in place. Methods are replaced on their class
  (e.g. a dataclass __init__ after adding a field), module-level functions are skipped with a warning.

- Members of enums are not added, removed or changed (a warning is shown), but enum methods are updated.

- Renamings are not handled correctly.

- Dependent modules are not reloaded (functions and classes are updated in place, so they see the changes).

- New __slots__ can't be added to existing classes.


Info
======================

Original: http://svn.python.org/projects/sandbox/trunk/xreload/xreload.py
Note: it seems https://github.com/plone/plone.reload/blob/master/plone/reload/xreload.py enhances it (to check later)

Interesting alternative: https://code.google.com/p/reimport/

Alternative to reload().

This works by executing the module in a scratch namespace, and then patching classes, methods and
functions in place.  This avoids the need to patch instances.  New objects are copied into the
target namespace.

"""

import enum
import logging
import types

logger = logging.getLogger(__name__)

NO_DEBUG = 0
LEVEL1 = 1
LEVEL2 = 2

DEBUG = NO_DEBUG


# We must redefine it in Py3k if it's not already there
def execfile(file, glob=None, loc=None):
    if glob is None:
        import sys

        glob = sys._getframe().f_back.f_globals
    if loc is None:
        loc = glob

    import tokenize

    with tokenize.open(file) as stream:
        contents = stream.read()

    # execute the script (note: it's important to compile first to have the filename set in debug mode)
    exec(compile(contents + "\n", file, "exec"), glob, loc)


def write_err(*args):
    logger.debug("code reload: %s", " ".join(str(a) for a in args))


def notify_info0(*args):
    write_err(*args)


def notify_info(*args):
    if DEBUG >= LEVEL1:
        write_err(*args)


def notify_info2(*args):
    if DEBUG >= LEVEL2:
        write_err(*args)


def notify_error(*args):
    write_err(*args)


# =======================================================================================================================
# code_objects_equal
# =======================================================================================================================
def code_objects_equal(code0, code1):
    for d in dir(code0):
        # co_lnotab is deprecated (and derived from line information, which is ignored anyway)
        if d.startswith("_") or "line" in d or d in ("replace", "co_positions", "co_qualname", "co_lnotab"):
            continue
        value0 = getattr(code0, d)
        # methods (e.g. co_branches in Python 3.14) never compare equal between two code objects
        if callable(value0):
            continue
        if value0 != getattr(code1, d):
            return False
    return True


# =======================================================================================================================
# xreload
# =======================================================================================================================
def xreload(mod):
    """Reload a module in place, updating classes, methods and functions.

    mod: a module object

    Returns a boolean indicating whether a change was done.

    Raises the exception raised while executing the new module code (e.g. SyntaxError), in which case nothing
    was updated. Use `Reload` directly to also inspect the warnings collected during the update.
    """
    r = Reload(mod)
    r.apply()
    if r.error is not None:
        raise r.error
    return r.found_change


# This isn't actually used... Initially I planned to reload variables which are immutable on the
# namespace, but this can destroy places where we're saving state, which may not be what we want,
# so, we're being conservative and giving the user hooks if he wants to do a reload.
#
# immutable_types = [int, str, float, tuple] #That should be common to all Python versions
#
# for name in 'long basestr unicode frozenset'.split():
#     try:
#         immutable_types.append(__builtins__[name])
#     except:
#         pass #Just ignore: not all python versions are created equal.
# immutable_types = tuple(immutable_types)


# =======================================================================================================================
# Reload
# =======================================================================================================================
class Reload:
    def __init__(self, mod, mod_name=None, mod_filename=None):
        self.mod = mod
        if mod_name:
            self.mod_name = mod_name
        else:
            self.mod_name = mod.__name__ if mod is not None else None

        if mod_filename:
            self.mod_filename = mod_filename
        else:
            self.mod_filename = mod.__file__ if mod is not None else None

        self.found_change = False
        # problems that did not stop the reload (e.g. attributes that could not be updated)
        self.warnings = []
        # names added to the module or its classes (e.g. 'new_function', 'MyClass.new_method')
        self.added = []
        # functions and methods whose code changed (e.g. 'function', 'MyClass.method')
        self.updated = []
        # exception raised while executing the new module code, if any
        self.error = None
        # ids of functions already updated, so that (recursive) closures are not followed twice
        self._visited = set()

    def _warn(self, msg):
        logger.warning("code reload (%s): %s", self.mod_name, msg)
        self.warnings.append(msg)

    def apply(self):
        mod = self.mod
        self._on_finish_callbacks = []
        try:
            # Get the module namespace (dict) early; this is part of the type check
            modns = mod.__dict__

            # Execute the code.  We copy the module dict to a temporary; then
            # clear the module dict; then execute the new code in the module
            # dict; then swap things back and around.  This trick (due to
            # Glyph Lefkowitz) ensures that the (readonly) __globals__
            # attribute of methods and functions is set to the correct dict
            # object.
            new_namespace = modns.copy()
            new_namespace.clear()
            if self.mod_filename:
                new_namespace["__file__"] = self.mod_filename
                try:
                    new_namespace["__builtins__"] = __builtins__
                except NameError:
                    raise  # Ok if not there.

            if self.mod_name:
                new_namespace["__name__"] = self.mod_name
                if new_namespace["__name__"] == "__main__":
                    # We do this because usually the __main__ starts-up the program, guarded by
                    # the if __name__ == '__main__', but we don't want to start the program again
                    # on a reload.
                    new_namespace["__name__"] = "__main_reloaded__"

            # keep the import metadata, otherwise relative imports cannot be resolved (and fail in packages)
            for attr in ("__package__", "__spec__", "__path__", "__loader__"):
                if attr in modns:
                    new_namespace[attr] = modns[attr]

            execfile(self.mod_filename, new_namespace, new_namespace)
            # Now we get to the hard part
            oldnames = set(modns)
            newnames = set(new_namespace)

            # Create new tokens (note: not deleting existing)
            for name in newnames - oldnames:
                notify_info0("Added:", name, "to namespace")
                self.found_change = True
                self.added.append(name)
                modns[name] = new_namespace[name]

            # Update in-place what we can
            for name in oldnames & newnames:
                self._update(modns, name, modns[name], new_namespace[name])

            self._handle_namespace(modns)

            for c in self._on_finish_callbacks:
                c()
            del self._on_finish_callbacks[:]
        except Exception as e:
            self.error = e
            logger.warning("Error reloading module %s", self.mod_name, exc_info=True)

    def _handle_namespace(self, namespace, is_class_namespace=False):
        on_finish = None
        if is_class_namespace:
            xreload_after_update = getattr(namespace, "__xreload_after_reload_update__", None)
            if xreload_after_update is not None:
                self.found_change = True

                def on_finish():
                    return xreload_after_update()

        elif "__xreload_after_reload_update__" in namespace:
            xreload_after_update = namespace["__xreload_after_reload_update__"]
            self.found_change = True

            def on_finish():
                return xreload_after_update(namespace)

        if on_finish is not None:
            # If a client wants to know about it, give him a chance.
            self._on_finish_callbacks.append(on_finish)

    def _update(self, namespace, name, oldobj, newobj, is_class_namespace=False):
        """Update oldobj, if possible in place, with newobj.

        If oldobj is immutable, this simply returns newobj.

        Args:
        ----
          oldobj: the object to be updated
          newobj: the object used as the source for the update
        """
        try:
            notify_info2("Updating: ", oldobj)
            if oldobj is newobj:
                # Probably something imported
                return

            if type(oldobj) is not type(newobj):
                # Cop-out: if the type changed, give up
                if name not in ("__builtins__",):
                    self._warn(f"Type of: {name} (old: {type(oldobj)} != new: {type(newobj)}) changed... Skipping.")
                return

            if isinstance(newobj, types.FunctionType):
                if is_class_namespace and oldobj.__code__.co_freevars != newobj.__code__.co_freevars:
                    # the code of a function cannot be swapped when its closure changed (e.g. a method that now
                    # uses super(), or a dataclass __init__ with a new field) - replace the method on the class
                    self._replace_method(namespace, name, oldobj, newobj)
                else:
                    self._update_function(oldobj, newobj, name)
                return

            if isinstance(newobj, property):
                self._update_property(namespace, name, oldobj, newobj, is_class_namespace)
                return

            if isinstance(newobj, types.MethodType):
                self._update_method(oldobj, newobj)
                return

            if isinstance(newobj, classmethod):
                self._update_classmethod(oldobj, newobj)
                return

            if isinstance(newobj, staticmethod):
                self._update_staticmethod(oldobj, newobj)
                return

            if hasattr(types, "ClassType"):
                classtype = (
                    types.ClassType,
                    type,
                )  # object is not instance of types.ClassType.
            else:
                classtype = type

            if isinstance(newobj, classtype):
                self._update_class(oldobj, newobj)
                return

            # New: dealing with metaclasses.
            if (
                hasattr(newobj, "__metaclass__")
                and hasattr(newobj, "__class__")
                and newobj.__metaclass__ == newobj.__class__
            ):
                self._update_class(oldobj, newobj)
                return

            # objects wrapping a function, e.g. functools.lru_cache
            old_wrapped, new_wrapped = _get_wrapped(oldobj), _get_wrapped(newobj)
            if old_wrapped is not None and new_wrapped is not None:
                self._update(None, name, old_wrapped, new_wrapped)
                cache_clear = getattr(oldobj, "cache_clear", None)
                if callable(cache_clear):
                    cache_clear()
                return

            if namespace is not None:
                # Check for the `__xreload_old_new__` protocol (don't even compare things
                # as even doing a comparison may break things -- see: https://github.com/microsoft/debugpy/issues/615).
                xreload_old_new = None
                if is_class_namespace:
                    xreload_old_new = getattr(namespace, "__xreload_old_new__", None)
                    if xreload_old_new is not None:
                        self.found_change = True
                        xreload_old_new(name, oldobj, newobj)

                elif "__xreload_old_new__" in namespace:
                    xreload_old_new = namespace["__xreload_old_new__"]
                    xreload_old_new(namespace, name, oldobj, newobj)
                    self.found_change = True

        except Exception as e:
            self._warn(f"Exception found when updating {name}. Proceeding for other items. Error: {e}")

    # All of the following functions have the same signature as _update()
    def _update_function(self, oldfunc, newfunc, name=None):
        """Update a function object in place, including the function it wraps and functions in its closure."""
        if id(oldfunc) in self._visited:
            return oldfunc
        self._visited.add(id(oldfunc))
        qualname = getattr(oldfunc, "__qualname__", repr(oldfunc))

        old_code = oldfunc.__code__
        new_code = newfunc.__code__
        if old_code.co_freevars != new_code.co_freevars:
            self._warn(
                f"Closure variables of '{name or qualname}' changed ({', '.join(old_code.co_freevars)} -> "
                f"{', '.join(new_code.co_freevars)}) - restart required to apply the change."
            )
            return oldfunc

        # functools.wraps sets __wrapped__ - keep it pointing to the original function, which is updated in place
        old_wrapped = oldfunc.__dict__.get("__wrapped__")
        oldfunc.__doc__ = newfunc.__doc__
        oldfunc.__dict__.update(newfunc.__dict__)
        if old_wrapped is not None:
            oldfunc.__wrapped__ = old_wrapped
            new_wrapped = newfunc.__dict__.get("__wrapped__")
            if isinstance(old_wrapped, types.FunctionType) and isinstance(new_wrapped, types.FunctionType):
                self._update(None, name, old_wrapped, new_wrapped)

        if not code_objects_equal(old_code, new_code):
            notify_info0("Updated function code:", oldfunc)
            oldfunc.__code__ = new_code
            self.found_change = True
            self.updated.append(qualname)

        oldfunc.__defaults__ = newfunc.__defaults__
        oldfunc.__kwdefaults__ = newfunc.__kwdefaults__

        # functions captured by the closure (e.g. the function decorated by a decorator without functools.wraps)
        for old_cell, new_cell in zip(oldfunc.__closure__ or (), newfunc.__closure__ or ()):
            try:
                old_value, new_value = old_cell.cell_contents, new_cell.cell_contents
            except ValueError:  # empty cell
                continue
            if isinstance(old_value, types.FunctionType) and isinstance(new_value, types.FunctionType):
                self._update(None, name, old_value, new_value)
        return oldfunc

    def _replace_method(self, oldclass, name, oldfunc, newfunc):
        """Replace a method on `oldclass` by `newfunc`, which uses the module globals and refers to `oldclass`."""
        replacement = _rebuild_function(newfunc, oldfunc.__globals__)
        if "__class__" in replacement.__code__.co_freevars:
            # zero-argument super() must refer to the class that is kept, not the temporary new one
            index = replacement.__code__.co_freevars.index("__class__")
            replacement.__closure__[index].cell_contents = oldclass
        setattr(oldclass, name, replacement)
        notify_info0("Replaced method:", name, "of", oldclass)
        self.found_change = True
        self.updated.append(getattr(replacement, "__qualname__", name))

    def _update_property(self, namespace, name, oldprop, newprop, is_class_namespace):
        """Update the accessors of a property in place, replacing the property if accessors were added or removed."""
        accessors = ("fget", "fset", "fdel")
        for attr in accessors:
            old_func, new_func = getattr(oldprop, attr), getattr(newprop, attr)
            if old_func is not None and new_func is not None:
                self._update(None, name, old_func, new_func)

        changed = [attr for attr in accessors if (getattr(oldprop, attr) is None) != (getattr(newprop, attr) is None)]
        if not changed or not is_class_namespace:
            return
        functions = []
        for attr in accessors:
            old_func, new_func = getattr(oldprop, attr), getattr(newprop, attr)
            if new_func is None:
                functions.append(None)
            elif old_func is not None:
                functions.append(old_func)
            elif isinstance(new_func, types.FunctionType):
                functions.append(_rebuild_function(new_func, self.mod.__dict__))
            else:
                functions.append(new_func)
        setattr(namespace, name, property(*functions, newprop.__doc__))
        notify_info0("Replaced property:", name, "of", namespace)
        self.found_change = True
        self.updated.append(f"{getattr(namespace, '__qualname__', namespace)}.{name}")

    def _update_method(self, oldmeth, newmeth):
        """Update a method object."""
        # XXX What if im_func is not a function?
        if hasattr(oldmeth, "im_func") and hasattr(newmeth, "im_func"):
            self._update(None, None, oldmeth.im_func, newmeth.im_func)
        elif hasattr(oldmeth, "__func__") and hasattr(newmeth, "__func__"):
            self._update(None, None, oldmeth.__func__, newmeth.__func__)
        return oldmeth

    def _update_class(self, oldclass, newclass):
        """Update a class object."""
        olddict = oldclass.__dict__
        newdict = newclass.__dict__

        # enum members are instances of their class, so they cannot be updated in place
        skipped = set(DATACLASS_ATTRIBUTES)
        if isinstance(oldclass, enum.EnumMeta) and isinstance(newclass, enum.EnumMeta):
            skipped |= self._check_enum_members(oldclass, newclass)

        oldnames = set(olddict) - skipped
        newnames = set(newdict) - skipped

        for name in newnames - oldnames:
            setattr(oldclass, name, newdict[name])
            notify_info0("Added:", name, "to", oldclass)
            self.found_change = True
            self.added.append(f"{getattr(oldclass, '__qualname__', oldclass)}.{name}")

        # Note: not removing old things...
        # for name in oldnames - newnames:
        #    notify_info('Removed:', name, 'from', oldclass)
        #    delattr(oldclass, name)

        for name in (oldnames & newnames) - {"__dict__", "__doc__"}:
            self._update(
                oldclass,
                name,
                olddict[name],
                newdict[name],
                is_class_namespace=True,
            )

        self._update_dataclass(oldclass, olddict, newdict)

        old_bases = getattr(oldclass, "__bases__", None)
        new_bases = getattr(newclass, "__bases__", None)
        if str(old_bases) != str(new_bases):
            self._warn(f"Changing the hierarchy of a class is not supported. {oldclass} may be inconsistent.")

        self._handle_namespace(oldclass, is_class_namespace=True)

    def _check_enum_members(self, oldclass, newclass):
        """Warn if the members of an enum changed. Returns the names of all members."""
        old_members = dict(oldclass.__members__)
        new_members = dict(newclass.__members__)
        added = [name for name in new_members if name not in old_members]
        removed = [name for name in old_members if name not in new_members]
        changed = []
        for name in old_members.keys() & new_members.keys():
            try:
                if old_members[name].value != new_members[name].value:
                    changed.append(name)
            # - values that cannot be compared are assumed to be unchanged
            except Exception:
                pass
        if added or removed or changed:
            details = ", ".join(
                f"{label}: {', '.join(sorted(names))}"
                for label, names in (("added", added), ("removed", removed), ("changed", changed))
                if names
            )
            self._warn(
                f"Members of enum '{getattr(oldclass, '__qualname__', oldclass)}' changed ({details}) - "
                "restart required to apply the change."
            )
        return set(old_members) | set(new_members)

    def _update_dataclass(self, oldclass, olddict, newdict):
        """Copy the dataclass metadata (fields, parameters), so that e.g. new fields are known."""
        if "__dataclass_fields__" not in newdict:
            return
        if list(olddict.get("__dataclass_fields__", {})) != list(newdict["__dataclass_fields__"]):
            self.found_change = True
        for attr in DATACLASS_ATTRIBUTES:
            if attr in newdict:
                setattr(oldclass, attr, newdict[attr])

    def _update_classmethod(self, oldcm, newcm):
        """Update a classmethod update."""
        # While we can't modify the classmethod object itself (it has no
        # mutable attributes), we *can* extract the underlying function
        # (by calling __get__(), which returns a method object) and update
        # it in-place.  We don't have the class available to pass to
        # __get__() but any object except None will do.
        self._update(None, None, oldcm.__get__(0), newcm.__get__(0))

    def _update_staticmethod(self, oldsm, newsm):
        """Update a staticmethod update."""
        # While we can't modify the staticmethod object itself (it has no
        # mutable attributes), we *can* extract the underlying function
        # (by calling __get__(), which returns it) and update it in-place.
        # We don't have the class available to pass to __get__() but any
        # object except None will do.
        self._update(None, None, oldsm.__get__(0), newsm.__get__(0))


# class attributes describing a dataclass, which are replaced on reload
DATACLASS_ATTRIBUTES = ("__dataclass_fields__", "__dataclass_params__", "__match_args__")


def _get_wrapped(obj):
    """Return the function wrapped by `obj` (e.g. a functools.lru_cache wrapper), or None."""
    try:
        attributes = object.__getattribute__(obj, "__dict__")
    except AttributeError:
        return None
    wrapped = attributes.get("__wrapped__") if isinstance(attributes, dict) else None
    return wrapped if isinstance(wrapped, types.FunctionType) else None


def _rebuild_function(func, globals_):
    """Return a copy of `func` that uses `globals_` (e.g. the module namespace instead of the temporary one)."""
    rebuilt = types.FunctionType(func.__code__, globals_, func.__name__, func.__defaults__, func.__closure__)
    rebuilt.__kwdefaults__ = func.__kwdefaults__
    rebuilt.__qualname__ = func.__qualname__
    rebuilt.__doc__ = func.__doc__
    rebuilt.__module__ = func.__module__
    rebuilt.__dict__.update(func.__dict__)
    return rebuilt
