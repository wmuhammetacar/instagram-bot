def json_serial(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)
