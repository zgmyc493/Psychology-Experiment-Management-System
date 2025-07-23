from flask import Blueprint

superadmin = Blueprint('superadmin', __name__)

from . import views 