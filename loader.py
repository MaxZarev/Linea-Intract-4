import asyncio


class SingletonMeta(type):
    """Метакласс для создания синглтонов"""
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class ConfigSingleton(metaclass=SingletonMeta):
    """Создание конфига в одном экземпляре"""

    def __init__(self):
        from utils import load_config, create_w3
        self.config = load_config()
        self.w3 = create_w3(self.config.rpc_linea)
        self.semaphore = asyncio.Semaphore(self.config.threads)
        self.lock = asyncio.Lock()


config = ConfigSingleton().config
w3 = ConfigSingleton().w3
semaphore = asyncio.Semaphore(config.threads)
lock = asyncio.Lock()
