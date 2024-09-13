class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class ConfigSingleton(metaclass=SingletonMeta):
    def __init__(self):
        from utils import load_config
        from utils import setup
        self.config = load_config()
        setup()


config = ConfigSingleton().config
