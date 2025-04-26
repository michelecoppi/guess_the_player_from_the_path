CACHE = {
    "current_day": None,
    "image_url": None,
    "correct_answers": [],
    "difficulty": None,
    "first_correct_user": False
}

def get_cache():
    return CACHE

def set_cache(data: dict):
    global CACHE
    CACHE.update(data)