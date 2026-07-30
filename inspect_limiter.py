import inspect
from flask_limiter import Limiter
print(Limiter)
print(inspect.signature(Limiter))
print(inspect.signature(Limiter.__init__))
