from tortoise import Model, fields


class Accounts(Model):
    profile_number = fields.IntField(max_length=255)
    address = fields.CharField(max_length=255, unique=True)
    quest_1_status = fields.BooleanField(default=False)
    quest_2_status = fields.BooleanField(default=False)
    quest_3_status = fields.BooleanField(default=False)
    quest_4_status = fields.BooleanField(default=False)

    class Meta:
        table = "accounts"

    @classmethod
    async def get_account(cls, profile_number: int) -> "Accounts":
        """
        Получает аккаунт по номеру профиля
        :param profile_number:  номер профиля
        :return:
        """
        return await cls.get_or_none(profile_number=profile_number)

    @classmethod
    async def get_accounts(cls) -> list["Accounts"]:
        """
        Получает список всех аккаунтов
        :return:  список аккаунтов
        """
        return await cls.all()

    @classmethod
    async def create_account(cls, profile_number: int, address: str) -> None:
        """
        Создает аккаунт в базе данных
        :param profile_number:  номер профиля
        :param address:  адрес кошелька
        :return:  None
        """
        account = await cls.get_account(profile_number=profile_number)
        if account is None:
            await cls.create(profile_number=profile_number, address=address, )

    @classmethod
    async def change_status(cls, profile_number: int, quest: int) -> None:
        """
        Изменяет статус квеста по номеру профиля и номеру квеста
        :param profile_number:  номер профиля
        :param quest:  номер квеста
        :return:  None
        """
        account = await cls.get_account(profile_number=profile_number)
        if account is not None:
            if quest == 1:
                account.quest_1_status = True
            elif quest == 2:
                account.quest_2_status = True
            elif quest == 3:
                account.quest_3_status = True
            elif quest == 4:
                account.quest_4_status = True
            await account.save()

    @classmethod
    async def get_status(cls, profile_number: int, quest: int) -> bool:
        """
        Проверяет статус квеста по номеру профиля и номеру квеста
        :param profile_number:  номер профиля
        :param quest:  номер квеста
        :return:  статус квеста
        """
        account = await cls.get_account(profile_number=profile_number)
        if account is not None:
            if quest == 1:
                return account.quest_1_status
            elif quest == 2:
                return account.quest_2_status
            elif quest == 3:
                return account.quest_3_status
            elif quest == 4:
                return account.quest_4_status
        return False

    @classmethod
    async def get_statuses(cls, profile_number: int):
        """
        Проверяет все статусы квестов
        :param profile_number: номер профиля
        :return: True если все квесты выполнены, иначе False
        """
        account = await cls.get_account(profile_number=profile_number)
        if account is not None:
            return all([
                account.quest_1_status,
                account.quest_2_status,
                account.quest_3_status,
                account.quest_4_status
            ])
