# thread_local
This module inspired by Flask, threading.local and werkzeug.local local object implementation.

See code:

  <a>https://github.com/python/cpython/blob/master/Lib/_threading_local.py</a>
  
  <a>http://werkzeug.pocoo.org/docs/0.12/local</a>
 
The module provides local context object with manager and proxy helpers.
Local context object is a special object which defines globally providing
ability to thread-safe access and manipulation with it attributes.
CRUD operation set guarantied :)

E.g. you can use one generally global object with attribute values would be local
and separated to each thread without any interference.
