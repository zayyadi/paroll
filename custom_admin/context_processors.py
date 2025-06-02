# custom_admin/context_processors.py
from .admin_config import registered_models
import re # Import re module

def custom_admin_nav(request):
    # A more robust way to check if we are in the custom admin
    # This regex matches /admin/custom/ or /admin/custom/anything
    if request.user.is_staff and re.match(r'^/admin/custom(/.*)?$', request.path):
        return {'custom_admin_models_nav': registered_models}
    return {}
