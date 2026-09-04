from flask import Blueprint

api = Blueprint("api", __name__, url_prefix="/api")

from app.api import plans  # noqa: E402, F401
from app.api import auth  # noqa: E402, F401
from app.api import tasks  # noqa: E402, F401
from app.api import executions  # noqa: E402, F401
from app.api import reflections  # noqa: E402, F401
from app.api import rule_changes  # noqa: E402, F401
from app.api import export  # noqa: E402, F401
from app.api import account  # noqa: E402, F401
