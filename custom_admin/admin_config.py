# custom_admin/admin_config.py
registered_models = {} # Will be structured as {app_label: [model_info_dict, ...]}

def register_model(model):
    app_label = model._meta.app_label
    model_name = model._meta.model_name
    
    if app_label not in registered_models:
        registered_models[app_label] = []
        
    # Check if model already registered for this app_label
    for m_info in registered_models[app_label]:
        if m_info['model_name'] == model_name:
            return # Already registered

    registered_models[app_label].append({
        'model': model, # Store the actual model class
        'model_name': model_name,
        'verbose_name': model._meta.verbose_name,
        'verbose_name_plural': model._meta.verbose_name_plural,
    })
