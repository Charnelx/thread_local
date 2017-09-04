"""
This module inspired by Flask, threading.local and werkzeug.local implementation
See code:
https://github.com/python/cpython/blob/master/Lib/_threading_local.py
http://werkzeug.pocoo.org/docs/0.12/local/

The module provides local context object with manager and proxy helpers.
Local context object is a special object which defines globally providing
ability to thread-safe access and manipulation with it attributes.
CRUD operation set guarantied :)

E.g. you can use one generally global object with attribute values would be local
and separated to each thread without any interference.

Simple and thou useless example in main thread:

    >>> manager = BaseContextManager()
    >>> local = LocalProxy(manager)

    >>> data = local()
    >>> data.results = 99
    >>> print(data.results)
    99

    >>> data.results = 0
    >>> print(data.results)
    0

    >>> del data.results
    >>> print(data.results)
    None

Still nothing to see here but if we dive deep into threads..:

    >>> from concurrent import futures

Lets define attribute global variable:

    >>> def func(n):
    ...     results = n
    ...     return results
    ...
    >>> data = local()
    >>> results = data.results = 99

And run function 'func' in ten separate threads:

    >>> fs = []
    >>> with futures.ThreadPoolExecutor(10) as executor:
    ...     for i in range(10):
    ......      fs.append(executor.submit(func, i))
    ...     for future in futures.as_completed(fs):
    ......      print(future.result())
    1
    0
    3
    4
    2
    5
    6
    7
    8
    9

Print main thread result variable value:

    >>> print(results)
    99

As we can see the value of variable results is independent between each thread.
Any changes made to it value in any context (thread context) are not affecting
each other.

Furthermore, you can access __dict__ attribute of local context object and get
only context-defined attributes:

    >>> print(data.__dict__())
    {'results': 99}

Note that __dict__ is method, not property/class attribute and thou it need to be called!

Also, local context object support attribute delete operation. Just as simple
as expected:

    >>> del data.results
    >>> print(data.results)
    None

Another use-case is to implement own ContextLocal and LocalProxy class for
example to add default arguments for local context objects:

    >>> class ModLocal(ContextLocal):
    ...
    ...     def __init__(self, manager, **kwargs):
    ......      {manager.set(self, k, v) for k,v in kwargs.items()}

    >>> class ModProxy(LocalProxy):
    ...     def __init__(self, manager):
    ......      self.manage = manager
    ...
    ...     def __call__(self, **kwargs):
    ......      return Modified(manager, **kwargs)

    >>> manager = BaseContextManager()
    >>> local = ModProxy(manager)
    >>> data = local(color='red')
    >>> print(data.color)
    red

BaseContextManager could be subclassed too. Use-cases are:
-   implementing read-only variables aka constants
-   redesigning descriptors logic
-   improve thread control functionality
-   etc

"""
from threading import RLock, get_ident


class ContextLocal(object):
    """
    ContextLocal class implements thread-safe local context object.
    Each time you add attribute to such object - it's bound to
    thread within the context of which this variable was assigned.
    """

    def __new__(cls, manager: object, *args, **kwargs):
        """
        This method run before class instantiated to bind each new instance
        with context manager and store special meta attributes.

        :param manager: BaseContextManager
        :param args: object, *
        :param kwargs: **
        :return: object
        """

        # case: since Py 2.5 object __init__ method accept no arguments
        # this check should prevent creating instance with init arguments
        # but without own __init__ method implementation
        if (args or kwargs) and (cls.__init__ is object.__init__):
            raise TypeError("Initialization arguments are not supported")

        self = super().__new__(cls)
        id = manager.ident_func()
        name = cls.__name__

        object.__setattr__(self, '_{}__manager'.format(name), manager)
        object.__setattr__(self, '_{}__largs'.format(name), (args, kwargs))
        object.__setattr__(self, '_{}__lock'.format(name), RLock())
        object.__setattr__(self, '__name__', name)

        attrs_dict = object.__getattribute__(self, '__dict__')
        manager.register(attrs_dict, id)
        return self

    def __getattribute__(self, name):
        cls_name = object.__getattribute__(self, '__name__')
        lock = object.__getattribute__(self, '_{}__lock'.format(cls_name))
        with lock:
            manager = object.__getattribute__(self, '_{}__manager'.format(cls_name))
            return manager.get(name)

    def __setattr__(self, name, value):
        cls_name = object.__getattribute__(self, '__name__')
        lock = object.__getattribute__(self, '_{}__lock'.format(cls_name))
        with lock:
            manager = object.__getattribute__(self, '_{}__manager'.format(cls_name))
            manager.set(self, name, value)

    def __delattr__(self, name):
        cls_name = object.__getattribute__(self, '__name__')
        lock = object.__getattribute__(self, '_{}__lock'.format(cls_name))
        with lock:
            manager = object.__getattribute__(self, '_{}__manager'.format(cls_name))
            manager.delete(name)

    def __del__(self):
        cls_name = object.__getattribute__(self, '__name__')
        lock = object.__getattribute__(self, '_{}__lock'.format(cls_name))
        with lock:
            manager = object.__getattribute__(self, '_{}__manager'.format(cls_name))
            if self in manager:
                manager.unregister()


class LocalProxy():
    """
    This class implements simple broker between current context
    and LocalContext object
    """

    def __init__(self, manager):
        """
        Manager argument will be used to instantiate ContextLocal
        class.

        :param manager:
        """

        self.manager = manager

    def __call__(self, *args, **kwargs):
        """
        Create ContextLocal object bound to specific manager.
        args/kwargs left for compatibility reasons. They haven't
        been used in basic ContextManager class.

        :param args: *
        :param kwargs: **
        :return: ContextLocal
        """
        if self.manager:
            return ContextLocal(self.manager, *args, **kwargs)
        raise AttributeError('No manager provided to manage local object')


class BaseContextManager(object):
    """
    This class is used to manage operations with access descriptors
    of local context objects.
    BaseContextManager perform separate and granular access to bunch
    of <thread: local_object>.
    E.g it proxies calls to appropriate objects from different contexts(threads).
    """

    SPECIAL_METHODS = ['manager', 'largs', 'lock']

    def __init__(self, ident_fn=None):
        """
        Initialize ContextManager with identification function. It used
        to identify thread which want to get/set/del attributes of local
        context object.
        Leave None to use threading get_ident() implementation.

        :param ident_fn: function or None
        """
        self.objects = {}
        self.ident_func = ident_fn if ident_fn else self._get_ident()
        self.lock = RLock()

    def __contains__(self, item):
        """
        Check if thread with ID(item) is managed by ContextManager.

        :param item: int
        :return: bool
        """

        # TODO: replace specific class check with abstract class check
        if isinstance(item, (ContextLocal,)):
            item = self.ident_func()

        return item in self.objects.keys()

    def register(self, attrs: dict, id=None):
        """
        This is the only method allowed to add(register) threads
        to store local object context in ContextManager objects dictionary.
        One's thread is registered it can store/access/remove local object
        context.

        Consider that threads could be registered not only by direct use
        of this method, but also just by assigning new attribute value to local
        context object - set() method will register thread automatically by
        invoking register() method.

        :param attrs: dict
        :param id: int or None
        :return: None
        """
        id = id if id else self.ident_func()
        attrs['__dict__'] = self._get_dict

        with self.lock:
            self.objects[id] = attrs

    def unregister(self, id=None):
        """
        This method invokes before local context object is deleted
        by garbage collector e.g when thread-owner of this object
        was deleted.

        :param id: str, int
        :return: None
        """

        id = id if id else self.ident_func()
        if isinstance(id, (str,)):
            id = int(id)
        assert isinstance(id, (int,)), '[id] should be of int type'

        if id in self:
            with self.lock:
                del self.objects[id]
            return
        raise AttributeError('Unable to find object with id {0}'.format(id))

    def get(self, name: str):
        """
        This method is a read access descriptor.
        get() invokes each time thread want to get local context
        object attribute value.

        Thread should be registered before calling this method or
        AttributeError will be raised.
        :param name: str
        :return: any
        """
        id = self.ident_func()
        if id in self:
            attrs = self.objects[id]
            return attrs.get(name)
        raise AttributeError ('No local context object found for process with id {0}'.format(id))

    def set(self, obj, name, value):
        """
        This method is a write access descriptor.
        set() invokes each time thread want to set local context
        object attribute value.

        Consider that even unregistered threads can set their local
        context object value - set() will automatically register such
        thread using register() method.

        Object which call this method need to patch it's own __dict__
        which leads to the need of 'obj' argument; also it needed
        to restrict access to __dict__ and __name__ attributes.

        :param obj:
        :param name:
        :param value:
        :return: None
        """
        id = self.ident_func()

        if name == '__dict__' or name == '__name__':
            raise AttributeError('{} object attribute {} is read-only'.format(type(obj).__name__, name))

        if id in self:
            attrs = self.objects[id]
            attrs[name] = value
        else:
            attrs = dict()
            attrs[name] = value

            old_attrs = object.__getattribute__(obj, '__dict__')
            for k in self._get_snames(obj):
                attrs[k] = old_attrs[k]

            self.register(attrs, id)

            # special attributes patch
            object.__setattr__(obj, '__dict__', attrs)
            object.__setattr__(obj, '__name__', type(obj).__name__)

            cls = type(obj)
            if cls.__init__ is not object.__init__:
                args, kwargs = object.__getattribute__(obj, '_{}__largs'.format(type(obj).__name__))
                cls.__init__(obj, self, *args, **kwargs)

    def delete(self, name: str):
        """
        This method is delete access descriptor.
        It invokes when thread is calling del operator on local
        context object attribute.

        :param name: str
        :return: None
        """
        id = self.ident_func()
        if id in self:
            attrs = self.objects[id]
            if name in attrs.keys() and (name != '__name__' and name != '__dict__'):
                with self.lock:
                    del attrs[name]
                    return
        raise KeyError('{}'.format(name))

    def _get_ident(self):
        """
        Return method to identify current (caller) thread.

        :return: function
        """
        return get_ident

    def _get_dict(self):
        """
        This method filter context object __dict__ attribute
        by removing special methods.
        It's needed to make thread retrieve only useful attributes
        without local context implementation helpers

        :return: dict
        """
        id = self.ident_func()

        if id in self:
            attrs = self.objects[id]
            try:
                name = attrs['__name__']
            except KeyError:
                raise AttributeError('Unable to retrieve class name') from None
            special_methods = self._get_snames(name)
            return {k: v for k, v in
                    filter(lambda item: item if item[0] not in special_methods
                                                and not item[0].startswith('__') else None, attrs.items())}

    def _get_snames(self, obj: object):
        """
        This method builds the list of special object attributes

        :param obj: str or instance
        :return: list
        """
        if isinstance(obj, (str,)):
            name = obj
        else:
            try:
                cls = object.__getattribute__(obj, '__class__')
                name = cls.__name__
            except:
                raise TypeError('Object is neither instance nor string. Cannot obtain __name__')
        return ['_{}__{}'.format(name, method) for method in self.SPECIAL_METHODS]