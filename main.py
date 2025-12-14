import asyncio
import random
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import FSInputFile
from openai import OpenAI
import logging
import os
from dotenv import load_dotenv
import aiohttp

from app.handlers import router
import app.keyboards as kb

#----------------------------------------------
# emoji_request_queue = asyncio.Queue()
#
# async def get_neuro_verdict(data):
#     import httpx
#     async with httpx.AsyncClient(timeout=40) as client:
#         r = await client.post(
#             "https://api.intelligence.io.solutions/api/v1/chat/completions",
#             json={...}  # твой payload
#         )
#         return r.json()["choices"][0]["message"]["content"]
#
# async def emoji_background_worker():
#     while True:
#         task = await emoji_request_queue.get()
#
#         game = task["game"]
#         bot = task["bot"]
#         chat_id = game.chat_id
#
#         verdict = await get_neuro_verdict(game.all_emojies)
#
#         await bot.send_message(chat_id, f"🤖 Оценка нейросети готова!\n\n{verdict}")
#
#         game.next_stage()
#
#         emoji_request_queue.task_done()
# ----------------------------------------------

load_dotenv()

# BOT_TOKEN = os.getenv("BOT_TOKEN")
# AI_TOKEN = os.getenv("AI_TOKEN")
BOT_TOKEN='8056179054:AAG7xDPYxFsuQZ15VZwFMlQ2ozqzoW8grWY'
AI_TOKEN='io-v2-eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJvd25lciI6ImFkNmJhNTI2LTY0NWItNDVmYi05NjYwLWU0YjBlZWNiYWM2OCIsImV4cCI6NDkxODg5Mzc2MX0.egN1W8UK7dqn55LtNhHyBwJlmH7qWJbMcSQTkXdXL0G5cJJnL7m98eAwG4Vou_78tXra_OXER7Njv3R7U6yBGQ'

logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN,
          default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

with open("topics.txt", "r", encoding="utf-8") as file:
    TOPICS_DATABASE = [line.strip() for line in file if line.strip()]

lobby = None
survivors_game = None
true_or_fake_game = None
writers_game = None
emoji_battle_game = None
random_court_game = None
fun_room_game = None
neuro_auction_game = None
games = ['Survivors', 'True or Fake', 'Writers', 'Emoji Battle', 'Random Court', 'Neuro Auction']
games_with_emoji = [
    ("🧟", "Survivors", "‍🔥"),
    ("🎭", "True or Fake", "❓"),
    ("✍️", "Writers", "📖"),
    ("⚔️", "Emoji Battle", "😄"),
    ("⚖️", "Random Court", "🎲"),
    #    ("🎉", "Fun Room НЕ ВЫБИРАТЬ!!!", "🤪")
    ("💰", "Neuro Auction", "🧠")
]
players = []


class Lobby:
    def __init__(self, chat_id, leader):
        self.chat_id = chat_id
        self.message_id = None
        self.leader = leader
        self.participants = [leader]
        self.game = None
        self.games_list = None

    async def refresh_message(self):
        text = self.get_lobby_text()
        image = FSInputFile("assets/images/lobby.png")

        if self.message_id is not None:
            try:
                await bot.delete_message(chat_id=self.chat_id, message_id=self.message_id)
                msg = await bot.send_photo(
                    chat_id=self.chat_id,
                    photo=image,
                    caption=text,
                    reply_markup=kb.join
                )
                self.message_id = msg.message_id
            except Exception as e:
                logger.error(f"Error editing message: {e}")
        else:
            msg = await bot.send_photo(
                chat_id=self.chat_id,
                photo=image,
                caption=text,
                reply_markup=kb.join
            )
            self.message_id = msg.message_id

    def get_lobby_text(self):
        participants = "\n".join(
            [f"👑 {p.full_name}" if p.id == self.leader.id else f"👤 {p.full_name}"
             for p in self.participants]
        )

        return (
            f"🎮 Лобби для игры с AI\n\n"
            f"Создатель: {self.leader.full_name}\n\n"
            f"Участники ({len(self.participants)}):\n{participants}\n\n"
            f"<b>Лидер</b> может начать игру командой \n{'-' * 11}/start{'-' * 11}\n\n"
            f"<b>Ты</b> можешь присоединиться командой \n{'-' * 11}/join{'-' * 12}"
        )

    async def choose_game(self):
        #num_games = min(3, len(games))
        #self.games_list = random.sample(games, num_games)

        width = 20
        text = "⌚Время выбирать игру!\n\n🕹️Выберите игру:\n" + "\n".join(
            [
                f"{i + 1}. <code>{game[0]}{'-' * ((width - len(game[1])) // 2)}{game[1]}{'-' * ((width - len(game[1])) // 2)}{game[2]}</code>"
                for i, game in enumerate(games_with_emoji)]
        )

        await bot.send_message(
            chat_id=self.chat_id,
            text=text,
            reply_markup=kb.choose_game
        )


class SurvivorsGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        random.shuffle(self.players)
        self.round = 1
        self.max_rounds = 5
        self.results = {player.id: [] for player in players}
        self.current_theme = ""
        self.current_themes = []
        self.player_turn = None
        self.strategies = {}
        self.evaluated_strategies = {str(player.id): [] for player in players}
        self.theme_message_id = None
        self.time_left = 120

    def next_round(self):
        self.round += 1
        self.current_theme = ""
        self.current_themes = []
        self.player_turn = None
        self.strategies = {}
        self.theme_message_id = None
        self.evaluated_strategies = {str(player.id): [] for player in players}

    async def start_game(self):
        text = (
            f"👋 Добро пожаловать в игру <b>Выжившие</b>!\n\n"
            f"🤖 В этой игре вы будете придумывать стратегии выживания в различных ситуациях.\n"
            f"💬 Игроки будут выбирать ситуацию, а бот оценивать их стратегии. Удачи!"
        )

        await bot.send_message(chat_id=self.chat_id, text=text)

    async def choose_theme(self):
        self.player_turn = self.players[0]
        self.players = self.players[1:] + [self.players[0]]
        self.current_themes = random.sample(TOPICS_DATABASE, 3)

        text = (
                f"🎤 {self.player_turn.full_name}, выберите тему:\n"
                + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(self.current_themes))
        )

        msg = await bot.send_message(
            chat_id=self.chat_id,
            text=text,
            reply_markup=kb.theme
        )
        self.theme_message_id = msg.message_id

    async def own_theme(self):
        text = (
            f"✏️{self.player_turn.full_name}, напиши свою тему"
        )

        await bot.edit_message_text(
            chat_id=self.chat_id,
            text=text,
            message_id=self.theme_message_id
        )

    async def confirm_theme(self):
        text = (
            f"✍️Напиши свою стратегию выживания\n\n"
            f"📜Тема: <b>{self.current_theme}</b>\n\n\n"
            f"👥Игроков прислало стратегии: {len(self.strategies)}/{len(self.players)}\n\n"
        )

        await bot.edit_message_text(
            chat_id=self.chat_id,
            text=text,
            message_id=self.theme_message_id
        )

    async def update_states(self):
        text = (
            f"✍️Напиши свою стратегию выживания\n\n"
            f"📜Тема: <b>{self.current_theme}</b>\n"
            f"👥Игроков прислало стратегии: {len(self.strategies)}/{len(self.players)}\n\n"
        )

        if len(self.strategies) == len(self.players) - 1:
            missing_player = next(player for player in self.players if player.id not in self.strategies)
            text += f"Ждём стратегию от: {missing_player.full_name}"

        await bot.edit_message_text(
            chat_id=self.chat_id,
            text=text,
            message_id=self.theme_message_id
        )

    async def evaluate_strategies_message(self):
        evaluated_strategies = await self.evaluate_strategies()

        for player in self.players:
            result_text = (
                f"👤 {player.full_name}\n"
                f"📜 Стратегия: {self.strategies[player.id]}\n\n"
                f"📖 История:\n{evaluated_strategies[str(player.id)][0]}\n\n"
                f"🔍 Вердикт: {'❤️ Выжил' if evaluated_strategies[str(player.id)][1] else '💀 Погиб'}"
            )

            survived = True if evaluated_strategies[str(player.id)][1] else False
            self.results[player.id].append(survived)
            await bot.send_message(chat_id=self.chat_id, text=result_text)

        await self.results_round()

    async def evaluate_strategies(self):
        try:
            # prompt = (
            #     "Ты - бот, выносящий реалистичный вердикт в игре, где игроки придумывают стратегию выживания в "
            #     "различных ситуациях. Опиши развитие событий (4-6 предложений) в разговорном, непринуждённом стиле. "
            #     "Не пиши своих рассуждений ни в каком виде!. Мне нужна только одна история и вердикт. "
            #     "Если стратегия хорошая и может сработать - оставь в живых, иначе, придумай реалистичную ситуацию, "
            #     "где игрок погибает. Разбавь ответ юмором. Твоя задача, чтобы игрок погиб, однако ты должен "
            #     "справедливо оценивать "
            #     "ситуацию. Обязательно условия игрока, если они не дают ему фантастических преимуществ (например  "
            #     "бессмертие). Как пример, если игрок говорит, что в данной ситуации он ведёт себя аккуратно, он не "
            #     "может случайно споткнуться или наступить на что-то. Игрок может допускать небольшие ошибки в "
            #     "стратегии. Если игрок нарушает правила, выдавая себе невозможные способности, придумай реалистичное "
            #     "развитие событий. Учитывай, что фантастические предметы игрок может использовать (в пределах "
            #     "разумного), если указал более-менее реалистичный способ их создания/приобретения. Не выделяй текст\n"
            #     f"Тема раунда: {self.current_theme}\n, стратегия игрока: {strategy}\n"
            #     "ОБЯЗАТЕЛЬНО! Формат:\nИстория: [текст]\nВердикт: [Выжил/Погиб]")
            #
            # # Инициализация клиента
            # client = OpenAI(
            #     base_url="https://openrouter.ai/api/v1",
            #     api_key=AI_TOKEN
            # )
            #
            # # Асинхронный запрос с ожиданием ответа
            # completion = client.chat.completions.create(
            #     extra_headers={
            #         "HTTP-Referer": "https://mysite.com",
            #         "X-Title": "My Site",
            #     },
            #     extra_body={},
            #     #model="deepseek/deepseek-chat-v3-0324:free",
            #     model="deepseek/deepseek-r1:free",
            #     messages=[
            #         {
            #             "role": "user",
            #             "content": prompt
            #         }
            #     ]
            # )
            #
            # if completion and completion.choices:
            #     answer = completion.choices[0].message.content
            #     parts = answer.split('Вердикт:')
            #     story = parts[0].replace('История:', '').strip()
            #     survived = True if 'выжил' in parts[1].lower() else False
            #     return story, survived
            # else:
            #     print(completion.choices[0].message.content)
            #     return "⚠️ Автоматическая ошибка: история не сгенерирована.", False

            import requests

            strategies = ''
            for player in self.players:
                strategies += str(player.id) + ": "
                strategies += self.strategies[player.id] + "\n"

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": "deepseek-ai/DeepSeek-V3.2",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Ты - бот, выносящий реалистичный вердикт в игре, где игроки придумывают стратегию выживания в "
                            "различных ситуациях. Опиши развитие событий (4-6 предложений) в разговорном, непринуждённом стиле. "
                            "Не пиши своих рассуждений ни в каком виде!. Мне нужна только одна история и вердикт. "
                            "Если стратегия хорошая и может сработать - оставь в живых, иначе, придумай реалистичную ситуацию, "
                            "где игрок погибает. Разбавь ответ юмором. Твоя задача, чтобы игрок погиб, однако ты должен "
                            "справедливо оценивать "
                            "ситуацию. Обязательно учитывай условия игрока, если они не дают ему фантастических преимуществ (например  "
                            "бессмертие). Как пример, если игрок говорит, что в данной ситуации он ведёт себя аккуратно, он не "
                            "может случайно споткнуться или наступить на что-то. Игрок может допускать небольшие ошибки в "
                            "стратегии. Если игрок нарушает правила, выдавая себе невозможные способности, придумай реалистичное "
                            "развитие событий. Учитывай, что фантастические предметы игрок может использовать (в пределах "
                            "разумного), если указал более-менее реалистичный способ их создания/приобретения. Не выделяй текст, учитывай регистр.\n"
                            f"Тема раунда: {self.current_theme}\n, стратегии игроков: {strategies}\n"
                            "ОБЯЗАТЕЛЬНО! Формат:\nИгрок: [Имя_игрока]\nИстория: [текст]\nВердикт: [Выжил/Погиб]\n---\n")
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            text = data['choices'][0]['message']['content']

            try:
                parts = text.split("\n---\n")
                evaluated_strategies = {str(player.id): [] for player in players}
                for part in parts:
                    part_player = part.split('\n')
                    name = part_player[0].replace('Игрок:', '').strip()
                    story = part_player[1].replace('История:', '').strip()
                    survived = part_player[2].replace('Вердикт:', '').strip()
                    survived = True if 'выжил' in survived else False
                    evaluated_strategies[name] = [story, survived]

                return evaluated_strategies
            except:
                print(text)
                return f"⚠️ Ошибка обработки ответа", False

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки стратегии: {str(e)}", False

    async def results_round(self):
        text = f"Результаты раунда {self.round}:\n\n"
        for player in self.players:
            if self.results[player.id][-1]:
                text += f"❤️ {player.full_name} выжил!\n"
            else:
                text += f"💀 {player.full_name} погиб!\n"

        await bot.send_message(chat_id=self.chat_id, text=text)

        if self.round == self.max_rounds:
            await self.final_results()
        else:
            self.next_round()
            await self.choose_theme()

    async def final_results(self):
        global survivors_game

        winner = ['никто', 0]
        text = "🕹️Игра завершена! Общие результаты:\n\n"
        for player in self.players:
            wins = sum(1 for result in self.results[player.id] if result)
            if wins > winner[1]:
                winner = [player.full_name, wins]
            text += f"👤 {player.full_name}: выжил {wins} раз(а) из {self.max_rounds}❤️\n"

        text += f"\n🏆 Победитель: {winner[0]} с {winner[1]} выживанием(ями)!\n\n"
        await bot.send_message(chat_id=self.chat_id, text=text)
        survivors_game = None


class TrueOrFakeGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        self.round = 1
        self.max_rounds = 5
        self.results = {player.id: [] for player in players}
        self.votes = {}
        self.results = {player.id: [] for player in players}
        self.facts = {}
        self.current_fact = ""
        self.true_or_fake = None
        self.thematic = ""

    def next_round(self):
        self.round += 1
        self.current_fact = ""
        self.votes = {}

    async def start_game(self):
        text = (
            f"👋 Добро пожаловать в игру <b>Правда или Ложь</b>!\n\n"
            f"🤖 Бот будет генерировать факты, а вы должны будете угадать, правда это или ложь.\n"
            f"💬 Напишите 'правда' или 'ложь' в ответ на сообщение, чтобы проголосовать. Удачи!"
        )

        await bot.send_message(chat_id=self.chat_id, text=text)

    async def choose_thematic(self):
        text = (
            f"🎤 Лидер выбирает тематику фактов"
        )

        await bot.send_message(
            chat_id=self.chat_id,
            text=text,
        )

    async def write_fact(self):
        import app.handlers as handlers

        if self.facts == {}:
            self.facts = await self.get_facts()

        self.current_fact, self.true_or_fake = self.facts[self.round - 1][0], self.facts[self.round - 1][1]

        text = (
            f"🕹️Раунд {self.round} из {self.max_rounds}\n\n"
            f"🤖 Факт: {self.current_fact}\n\n"
            f"💬 Напишите 'правда' или 'ложь' в ответ на сообщение, чтобы проголосовать."
        )

        await bot.send_message(chat_id=self.chat_id,
                               text=text,
                               reply_markup=kb.answer
                               )
        handlers.true_or_fake_states = "waiting_for_choice"

    async def get_facts(self):
        try:
            # prompt = (
            #     "Ты - бот, который генерирует интересные факты для игры 'Правда или Ложь' на определённую тему. Твоя "
            #     "задача - придумать пять неправдоподобных, удивительных фактов, о которых может не знать множество "
            #     "людей и написать их. Факт иногда должен быть правдой, иногда выдумкой, главное, чтобы звучал "
            #     f"правдоподобно. Сейчас тематика фактов: '{self.thematic}'.\n\n"
            #     "ОБЯЗАТЕЛЬНО! Твой ответ должен выглядеть так:\n\nФакт: [текст]\nОтвет: [правда/ложь]\n\nФакт: ["
            #     "текст]\nОтвет: [правда/ложь]\n\nи тд\nОт себя ничего не добавляй и не выделяй текст(!). Ответ пиши "
            #     "только на русском языке")
            #
            # # Инициализация клиента
            # client = OpenAI(
            #     base_url="https://openrouter.ai/api/v1",
            #     api_key=AI_TOKEN
            # )
            #
            # # Асинхронный запрос с ожиданием ответа
            # completion = client.chat.completions.create(
            #     extra_headers={
            #         "HTTP-Referer": "https://mysite.com",
            #         "X-Title": "My Site",
            #     },
            #     extra_body={},
            #     model="deepseek/deepseek-r1:free",
            #     messages=[
            #         {
            #             "role": "user",
            #             "content": prompt
            #         }
            #     ]
            # )
            #
            # try:
            #     num = 0
            #     facts = {}
            #     answer = completion.choices[0].message.content
            #     facts_and_answers = answer.split('\n\n')
            #     for i in facts_and_answers:
            #         parts = i.split('Ответ:')
            #         fact = parts[0].replace('Факт:', '').strip()
            #         true_or_fake = True if 'правда' in parts[1].lower() else False
            #         facts[num] = (fact, true_or_fake)
            #         num += 1
            # except:
            #     print(completion.choices[0].message.content)
            #     return f"⚠️ Ошибка обработки ответа", False
            # return facts

            import requests

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": "deepseek-ai/DeepSeek-V3.2",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Ты - бот, который генерирует интересные факты для игры 'Правда или Ложь' на определённую тему. Твоя "
                            "задача - придумать пять неправдоподобных, удивительных фактов, о которых может не знать множество "
                            "людей и написать их. Факт иногда должен быть правдой, иногда выдумкой, главное, чтобы звучал "
                            f"правдоподобно. Сейчас тематика фактов: '{self.thematic}'.\n\n"
                            "ОБЯЗАТЕЛЬНО! Твой ответ должен выглядеть так:\n\nФакт: [текст]\nОтвет: [правда/ложь]\n\nФакт: ["
                            "текст]\nОтвет: [правда/ложь]\n\nи тд\nОт себя ничего не добавляй и не выделяй текст(!). Ответ пиши "
                            "только на русском языке")
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            text = data['choices'][0]['message']['content']

            try:
                num = 0
                facts = {}
                # answer = text.split('</think>\n')[1]
                facts_and_answers = text.split('\n\n')
                for i in facts_and_answers:
                    parts = i.split('Ответ:')
                    fact = parts[0].replace('Факт:', '').strip()
                    true_or_fake = True if 'правда' in parts[1].lower() else False
                    facts[num] = (fact, true_or_fake)
                    num += 1
            except:
                print("Ошибка")
                return f"⚠️ Ошибка обработки ответа", False

            return facts

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки стратегии: {str(e)}", False

    async def evaluate_votes(self):
        text = f"Результаты раунда {self.round}:\n\n"
        for player in self.players:
            text += f"⚖️ {player.full_name} проголосовал!\n"
            self.results[player.id].append(True if self.true_or_fake else False)
            # if self.votes[player.id]:
            #     text += f"⚖️ {player.full_name} проголосовал за <u>правду</u>!\n"
            #     self.results[player.id].append(True if self.true_or_fake else False)
            # else:
            #     text += f"🤥 {player.full_name} проголосовал за <u>ложь</u>!\n"
            #     self.results[player.id].append(True if not self.true_or_fake else False)

        text += "\n\n🤖 Факт был: " + ("<b>правдой</b>" if self.true_or_fake else "<b>ложью</b>") + "\n\n"

        await bot.send_message(chat_id=self.chat_id, text=text)

        if self.round == self.max_rounds:
            await self.final_results()
        else:
            self.next_round()
            await self.write_fact()

    async def final_results(self):
        global true_or_fake_game

        winner = ['никто', 0]
        text = "🕹️Игра завершена! Общие результаты:\n\n"
        for player in self.players:
            wins = sum(1 for result in self.results[player.id] if result)
            if wins > winner[1]:
                winner = [player.full_name, wins]
            text += f"👤 {player.full_name}: отгадал {wins} раз(а) из {self.max_rounds}\n"

        text += f"\n🏆 Победитель: <b>{winner[0]}</b> с {winner[1]} правильным(и) ответом(ами)!\n\n"

        await bot.send_message(chat_id=self.chat_id, text=text)
        true_or_fake_game = None


class WritersGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        self.num_sentence = 0
        self.max_rounds = 3
        self.round = 0
        self.max_sentences = (len(players) * self.max_rounds) + (self.max_rounds + 1)
        self.story = ""
        self.last_sentence = ""
        self.player_turn = None
        self.message_id = None
        self.last_sentence_id = None
        self.max_in_round = len(self.players) + 1

    async def next_sentence(self):
        self.num_sentence += 1
        self.player_turn = self.players[0]
        self.players = self.players[1:] + [self.players[0]]
        if self.message_id is not None:
            await bot.delete_message(chat_id=self.chat_id,
                                     message_id=self.message_id)

    async def start_game(self):
        text = ("👋Добро пожаловать в игру <b>Писатели</b>!\n\n"
                "🕹️В этой игре вы будете по очереди писать отрывок текста, который будет добавляться к общей истории.\n"
                "🤖В конце каждого круга, первое и последнее предложение будет генерировать бот. Удачи!")

        await bot.send_message(chat_id=self.chat_id,
                               text=text)

    async def write_history(self):
        import app.handlers as handlers

        if self.num_sentence % (len(players) + 1) == 0 or self.num_sentence == 0:
            msg = await bot.send_message(chat_id=self.chat_id,
                                         text=(f"🔁<b>Круг {self.round + 1}/{self.max_rounds}</b>\n"
                                               f"📒<b>Предложение {self.num_sentence - (self.max_in_round * self.round)}/{self.max_in_round}</b>\n\n"
                                               f"🤖Сейчас <u>бот</u> придумывает предложение...\n\n")
                                         )
            self.message_id = msg.message_id

            if self.num_sentence != 0:
                self.round += 1

            self.last_sentence = await self.get_AI_sentence()
            await self.confirm_sentence()
        else:
            msg = await bot.send_message(chat_id=self.chat_id,
                                         text=(f"🔁<b>Круг {self.round + 1}/{self.max_rounds}</b>\n"
                                               f"📒<b>Предложение {self.num_sentence - (self.max_in_round * self.round)}/{self.max_in_round}</b>\n\n"
                                               f"👤Игрок <u>{self.player_turn.full_name}</u> пишет предложение!\n\n"
                                               )
                                         )

            last_sentence_id = await bot.send_message(chat_id=self.player_turn.id,
                                   text=f"Предыдущее предложение: {self.last_sentence}")

            self.last_sentence_id = last_sentence_id.message_id
            self.message_id = msg.message_id
            handlers.writers_states = "waiting_for_sentence"

    async def clear_last_sentence(self):
        await bot.delete_message(chat_id=self.player_turn.id,
                                message_id=self.last_sentence_id)

    async def get_AI_sentence(self):
        try:
            # if self.num_sentence == 0:
            #     prompt = ("Ты - бот, который генерирует предложение для игры 'Писатели'. Твоя задача - придумать одно "
            #               "предложение, которое станет началом необычной, интересной, загадочной или смешной истории. "
            #               "Первое предложение может рассказывать о сказочном герое, компании ребят, что исследуют "
            #               "заброшенный дом или о чём-либо другом. Начало истории должно быть абсолютно случайным и "
            #               "завязано на случайном объекте, действии, существе, ситуации. Не повторяйся с началом "
            #               "других историй (если ты запоминаешь контекст разговора)."
            #               "Не пиши своих рассуждений ни в каком виде!. Мне нужно только одно предложение и не выделяй "
            #               "текст.")
            # elif self.num_sentence == self.max_sentences:
            #     prompt = (
            #         f"Ты - бот, который генерирует одно предложение для игры 'Писатели'. Твоя задача - придумать "
            #         f"предложение, которое будет неожиданно заканчивать историю. Можешь разбавить предложение юмором. "
            #         f"Не пиши своих рассуждений ни в каком виде!. Мне нужно только одно предложение и не выделяй "
            #         f"текст. Твоя задача - завершить историю, основываясь на общем тексте: '{self.story}'. Пришли "
            #         f"только одно предложение, которое ты придумал(!)."
            #     )
            # else:
            #     prompt = (
            #         f"Ты - бот, который генерирует одно предложение для игры 'Писатели'. Твоя задача - придумать предложение, "
            #         f"которое будет неожиданно заворачивать историю. Можешь разбавить предложение юмором. Не пиши своих рассуждений ни в каком виде!. Мне нужно "
            #         f"только одно предложение и не выделяй текст. Твоя задача - продолжить историю, основываясь на "
            #         f"общем тексте: '{self.story}'. Пришли только последнее предложение, которое ты придумал(!)."
            #     )
            #
            # client = OpenAI(
            #     base_url="https://openrouter.ai/api/v1",
            #     api_key=AI_TOKEN
            # )
            #
            # completion = client.chat.completions.create(
            #     extra_headers={
            #         "HTTP-Referer": "https://mysite.com",
            #         "X-Title": "My Site",
            #     },
            #     extra_body={},
            #     model="deepseek/deepseek-r1:free",
            #     messages=[
            #         {
            #             "role": "user",
            #             "content": prompt
            #         }
            #     ]
            # )
            #
            # if completion and completion.choices:
            #     text = completion.choices[0].message.content
            #     return text
            # else:
            #     print(completion.choices[0].message.content)
            #     return "⚠️ Автоматическая ошибка: история не сгенерирована.", False

            import requests

            if self.num_sentence == 0:
                prompt = ("Ты - бот, который генерирует предложение для игры 'Писатели'. Твоя задача - придумать одно "
                          "предложение, которое станет началом необычной, интересной, загадочной или смешной истории. "
                          "Первое предложение может рассказывать о сказочном герое, компании ребят, что исследуют "
                          "заброшенный дом или о чём-либо другом. Начало истории должно быть абсолютно случайным и "
                          "завязано на случайном объекте, действии, существе, ситуации. Не повторяйся с началом "
                          "других историй (если ты запоминаешь контекст разговора)."
                          "Не пиши своих рассуждений ни в каком виде!. Мне нужно только одно предложение и не выделяй "
                          "текст.")
            elif self.num_sentence == self.max_sentences - 1:
                prompt = (
                    f"Ты - бот, который генерирует одно предложение для игры 'Писатели'. Твоя задача - придумать "
                    f"предложение, которое будет неожиданно заканчивать историю. Можешь разбавить предложение юмором. "
                    f"Не пиши своих рассуждений ни в каком виде!. Мне нужно только одно предложение и не выделяй "
                    f"текст. Твоя задача - завершить историю, основываясь на предыдущем предложении: '{self.last_sentence}'. Пришли "
                    f"только одно предложение, которое ты придумал(!)."
                )
            else:
                prompt = (
                    f"Ты - бот, который генерирует одно предложение для игры 'Писатели'. Твоя задача - придумать предложение, "
                    f"которое будет неожиданно заворачивать историю. Можешь разбавить предложение юмором. Не пиши своих рассуждений ни в каком виде!. Мне нужно "
                    f"только одно предложение и не выделяй текст. Твоя задача - продолжить историю, основываясь на "
                    f"предыдущем предложении: '{self.last_sentence}'. Пришли только последнее предложение, которое ты придумал(!)."
                )

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": "deepseek-ai/DeepSeek-V3.2",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']

            # text = answer.split('/think\n')[1]
            text = answer

            return text

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки стратегии: {str(e)}", False

    async def confirm_sentence(self):
        self.story += " " + self.last_sentence

        await self.next_sentence()

        # text = (f"Вот придуманное предложение:\n\n"
        #         f" {self.last_sentence}")
        #
        # await bot.send_message(chat_id=self.chat_id,
        #                        text=text,
        #                        )

        if self.num_sentence == self.max_sentences:
            await self.get_results()
            return

        await self.write_history()

    async def get_results(self):
        text = f"🎉 Игра завершена! История:\n\n{self.story}"

        await bot.send_message(chat_id=self.chat_id,
                               text=text,
                               message_effect_id="5107584321108051014")


class EmojiBattleGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        self.round = 1
        self.max_rounds = 3
        self.emojies = {player.full_name: "" for player in players}
        self.all_emojies = {player.full_name: "" for player in players}
        self.results = {player.id: [] for player in players}
        self.thematic = ""
        self.message_id = None

    def next_round(self):
        self.round += 1
        self.thematic = ""
        self.emojies = {player.full_name: "" for player in players}

    async def start_game(self):
        text = ("👋Добро пожаловать в игру 'Эмодзи Битва'!\n\n"
                "🕹️ В этой игре вы будете придумывать наборы эмодзи, которые в наибольшей степени соответствуют "
                "заданной тематике. Удачи!")

        await bot.send_message(chat_id=self.chat_id,
                               text=text)

    async def start_round(self):
        await bot.send_message(chat_id=self.chat_id,
                               text=f"⏱️Нейросеть придумывает тематику для раунда...")

        self.thematic = await self.get_thematic()

        await self.start_timer()

    async def start_timer(self):
        import app.handlers as handlers

        text = (f"🕹️Раунд {self.round} из {self.max_rounds}\n\n"
                f"🤖 Тематика: {self.thematic}\n\n"
                f"💬 Напишите свой набор эмодзи, наиболее подходящий к данной тематике.\n\n"
                f"⏳У вас есть 30 секунд, чтобы придумать свой набор эмодзи и отправить его в чат!\n\n"
                )

        msg = await bot.send_message(chat_id=self.chat_id,
                                     text=text)
        self.message_id = msg.message_id

        timer_msg = await bot.send_message(chat_id=self.chat_id,
                                           text=f"⏱️Осталось: 30 секунд")
        timer_msg_id = timer_msg.message_id

        handlers.emoji_battle_states = "waiting_for_emoji"
        start_time = time.time()
        counter = 25
        while counter > -1 and not handlers.emoji_battle_states is None:
            elapsed_time = time.time() - start_time
            if elapsed_time >= 5:
                await bot.edit_message_text(chat_id=self.chat_id,
                                            message_id=timer_msg_id,
                                            text=f"⏱️Осталось: {counter} секунд")
                counter -= 5
                start_time = time.time()
            await asyncio.sleep(0.001)

        await bot.delete_message(chat_id=self.chat_id,
                                 message_id=timer_msg_id)

        if not handlers.emoji_battle_states is None:
            handlers.emoji_battle_states = None

            text = (f"🕹️Раунд {self.round} из {self.max_rounds}\n\n"
                    f"🤖 Тематика: {self.thematic}\n\n"
                    f"💬 Напишите свой набор эмодзи, наиболее подходящий к данной тематике.\n\n"
                    f"⏰Время вышло!"
                    )

            await bot.edit_message_text(chat_id=self.chat_id,
                                        message_id=self.message_id,
                                        text=text)

        await self.evaluate_emojies()

    async def get_thematic(self):
        try:
            # prompt = (
            #     "Ты - бот, который генерирует тематику для игры 'Эмодзи Битва'. Твоя задача - придумать одну "
            #     "тематику, которая будет интересной и необычной. Тематика должна быть связана с чем-то "
            #     "конкретным, например, 'фильмы', 'животные', 'еда' и т.д. Не пиши своих рассуждений ни в каком виде!. "
            #     "Мне нужно только одна тематика и не выделяй текст.")
            #
            # client = OpenAI(
            #     base_url="https://openrouter.ai/api/v1",
            #     api_key=AI_TOKEN
            # )
            #
            # completion = client.chat.completions.create(
            #     extra_headers={
            #         "HTTP-Referer": "https://mysite.com",
            #         "X-Title": "My Site",
            #     },
            #     extra_body={},
            #     model="deepseek/deepseek-r1:free",
            #     messages=[
            #         {
            #             "role": "user",
            #             "content": prompt
            #         }
            #     ]
            # )
            #
            # if completion and completion.choices:
            #     text = completion.choices[0].message.content
            #     return text
            # else:
            #     print(completion.choices[0].message.content)
            #     return "⚠️ Автоматическая ошибка: тематика не сгенерирована.", False

            import requests

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": "deepseek-ai/DeepSeek-V3.2",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Ты - бот, который генерирует тематику для игры 'Эмодзи Битва'. Твоя задача - придумать одну "
                            "случайную тематику, которая будет интересной, необычной, забавной или абсурдной."
                            "Тематика не должна быть связана с чем-то конкретным, например 'поход в кино', 'прогулка "
                            "с собакой', 'взрывная вечеринка' и т.д. Не пиши своих рассуждений ни в каком виде и не "
                            "выделяй текст!. Ты должен прислать только тематику - её текст (без любых эмодзи).")
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']

            # text = answer.split('</think>\n')[1]
            text = answer

            return text

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки тематики: {str(e)}", False

    async def evaluate_emojies(self):
        text = f"Результаты раунда {self.round}:\n\n"

        for player in self.players:
            text += f"👤 {player.full_name}: "
            if self.emojies[player.full_name] == "":
                text += "❌ Не отправил набор эмодзи!\n"
                self.results[player.id].append("0")
                continue
            verdict = await self.evaluate_emoji(self.emojies[player.full_name])
            text += verdict
            self.results[player.id].append(verdict.split('/')[0])
            text += f" - {self.emojies[player.full_name]}\n\n"

        await bot.send_message(chat_id=self.chat_id,
                               text=text)

        if self.round == self.max_rounds:
            await self.final_results()
        else:
            self.next_round()
            await self.start_round()

    async def evaluate_emoji(self, emoji):
        try:
            # prompt = (
            #     "Ты - бот, который оценивает набор эмодзи в игре 'Эмодзи Битва'. Твоя задача - оценить набор эмодзи, "
            #     "который игрок отправил на определённую тематику. Оцени набор эмодзи по шкале от 1 до 10, где 1 - "
            #     "это полный провал, а 10 - это идеальный набор эмодзи. Не пиши своих рассуждений ни в каком виде!. "
            #     "Мне нужно только оценка и не выделяй текст.")
            #
            # client = OpenAI(
            #     base_url="https://openrouter.ai/api/v1",
            #     api_key=AI_TOKEN
            # )
            #
            # completion = client.chat.completions.create(
            #     extra_headers={
            #         "HTTP-Referer": "https://mysite.com",
            #         "X-Title": "My Site",
            #     },
            #     extra_body={},
            #     model="deepseek/deepseek-r1:free",
            #     messages=[
            #         {
            #             "role": "user",
            #             "content": f"Тематика: {self.thematic}\nНабор эмодзи: {emoji}\n"
            #                        f"Оценка: [текст]"
            #         }
            #     ]
            # )

            import requests

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": "deepseek-ai/DeepSeek-V3.2",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Ты - бот, который оценивает набор эмодзи в игре 'Эмодзи Битва'. Твоя задача - оценить "
                            "набор эмодзи, который игрок отправил на определённую тематику. Оцени набор эмодзи по "
                            "шкале от 1 до 10, где 1 - это полный провал, а 10 - это идеальный набор эмодзи. Не пиши "
                            "своих рассуждений ни в каком виде!. Мне нужно только оценка и не выделяй текст. Твой "
                            "ответ должен выглядеть так: '{кол-во баллов}/10'. Ты должен достаточной строго оценивать "
                            "набор на соответвие с тематикой, но не занижай оценку, оценивай справедливо."
                            f"Тематика раунда: '{self.thematic}'. Набор эмодзи: '{emoji}'.")
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']

            # text = answer.split('</think>\n')[1]
            text = answer

            return text

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки эмодзи: {str(e)}", False

    async def final_results(self):
        global emoji_battle_game

        await bot.send_message(chat_id=self.chat_id,
                               text="🕹️Игра завершена! Оценка общих результатов...")

        winner = ['никто', 0]
        text = "🕹️Игра завершена! Общие результаты:\n\n"
        for player in self.players:
            wins = sum(int(result) for result in self.results[player.id])
            if wins > winner[1]:
                winner = [player.full_name, wins]
            text += f"👤 {player.full_name}: набрал {wins} баллов из {self.max_rounds * 10}❤️\n"

        text += f"\n🏆 Победитель: <b>{winner[0]}</b> с {winner[1]} баллом(ами)!\n\n"

        text += f"История его последней битвы:\n\n"
        text += await self.get_story(winner[0])

        await bot.send_message(chat_id=self.chat_id, text=text)
        emoji_battle_game = None

    async def get_story(self, winner):
        import requests

        url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_TOKEN}"
        }

        data = {
            # "model": "deepseek-ai/DeepSeek-R1-0528",
            "model": "deepseek-ai/DeepSeek-V3.2",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Придумай историю о битве, в которой победил игрок {winner}, основанную на наборе эмодзи, "
                        f"что игроки использовали в игре 'Эмодзи Битва'. Если игроков несколько, то они должны "
                        f"сражаться между собой. Не выделяй текст и не пиши размышлений!."
                        f"Вот эмодзи всех игроков: {self.all_emojies}.")
                }
            ]
        }

        response = requests.post(url, headers=headers, json=data)
        data = response.json()
        answer = data['choices'][0]['message']['content']

        # text = answer.split('/think\n\n')[1]
        text = answer

        return text


class RandomCourtGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        self.answers = []
        self.roles = {"Подсудимый": None, "Прокурор": None, "Адвокат": None}
        self.case = ""
        self.role_turn = None
        self.round = 1
        self.max_rounds = 5

    def next_round(self):
        self.case = ""
        self.round += 1

    async def start_game(self):
        text = (
            f"Добро пожаловать в игру <b>Случайный Суд</b>! ⚖️\n"
            f"В этой игре вы будете играть роли в суде, где каждый из вас будет выступать в роли подсудимого, "
            f"прокурора или адвоката.\n\n"
            f"Сейчас каждый должен определить свою роль.\n\n"
            f"•Подсудимый🧍‍♂️🚓\n"
            f"Главный герой «преступления», которого обвиняют. Может защищать себя или промолчать.\n\n"
            f"•Прокурор👨‍💼🔨\n"
            f"Обвинитель, который должен доказать вину подсудимого. Может задавать вопросы и делать выводы.\n\n"
            f"•Адвокат👨‍💼⚖️\n"
            f"Защитник подсудимого, который должен доказать его невиновность. Может задавать вопросы и делать выводы.\n\n"
            f"<s>•Свидетель</s>\n"
            f"<s>Можно выбрать, если игроков больше 3-х. Свидетель может быть как на стороне подсудимого, так и на стороне прокурора.</s>\n\n"
            f"•Судья👨‍⚖️\n"
            f"Судьёй будет выступать ИИ. Он вынесет окончательное решение, основываясь на предоставленных данных.\n\n"
        )

        await bot.send_message(chat_id=self.chat_id,
                               text=text,
                               reply_markup=kb.role)

    async def confirm_role(self, role, player):
        await bot.send_message(chat_id=self.chat_id,
                               text=f"Игрок {player} выбрал роль <b>{role}</b>.\n\n")

        if None not in self.roles.values():
            await bot.send_message(chat_id=self.chat_id,
                                   text=f"Все роли выбраны. Игра начинается!")
            await self.write_case()

    async def write_case(self):
        import app.handlers as handlers

        await bot.send_message(chat_id=self.chat_id,
                               text=f"⏱️Нейросеть придумывает случайный случай...")

        defendant_text, prosecutor_text, lawyer_text, self.case = await self.get_case()

        await bot.send_message(chat_id=self.roles["Подсудимый"].id,
                               text="Вы -- подсудимый🧍‍♂️🚓. Вот, что вы знаете:\n\n" + defendant_text)
        await bot.send_message(chat_id=self.roles["Прокурор"].id,
                               text="Вы -- прокурор👨‍💼🔨. Вот, что вы знаете:\n\n" + prosecutor_text)
        await bot.send_message(chat_id=self.roles["Адвокат"].id,
                               text="Вы -- адвокат👨‍💼⚖️. Вот, что вы знаете:\n\n" + lawyer_text)

        await bot.send_message(chat_id=self.chat_id,
                               text=f"В игру!\n"
                                    f"У вас есть 5 раундов, чтобы выяснить, кто прав, а кто виноват.\n\n"
                                    f"Обвиняется игрок <u>{self.roles["Подсудимый"].full_name}</u>.\n\n"
                                    f"Его защищает игрок <u>{self.roles["Адвокат"].full_name}</u>.\n\n"
                                    f"Обвиняет его игрок <u>{self.roles["Прокурор"].full_name}</u>.\n\n")

        self.role_turn = self.roles["Прокурор"]
        handlers.random_court_states = "waiting_for_prosecutor"

    async def next_turn(self):
        if self.role_turn == self.roles["Прокурор"]:
            self.role_turn = self.roles["Адвокат"]
        elif self.role_turn == self.roles["Подсудимый"]:
            self.role_turn = self.roles["Прокурор"]
        else:
            self.role_turn = self.roles["Подсудимый"]

        await bot.send_message(chat_id=self.chat_id,
                               text=f"🔁Раунд {self.round} из {self.max_rounds}\n\n"
                                    f"🗣️Сейчас говорит игрок <u>{self.role_turn.full_name}</u>.")

    async def get_case(self):
        try:
            import requests

            prompt = (
                "Ты - бот, который генерирует случайный случай для игры 'Случайный Суд'. Твоя задача - "
                "придумать один случай, который будет интересным и необычным. Ты должен распределить информацию "
                "об одной и той же истории между участниками: подсудимым, прокурором и адвокатом. Случай должен "
                "быть связан с чем-то конкретным, например, 'кража', 'убийство', 'разгром' и т.д. Учитывай, "
                "что кто-то может иметь неверные сведения (и, если например это обвиняемый, то и адвокат, возможно, "
                "имеет те же сведения, и наоборот). Также учитывай, что адвокат или прокурор может раздобыть некоторые данные ("
                "возможно даже нечестным путём, но об этом знает возможно лишь он). Помни, что в правильной "
                "истории нет лжи, в ней всё так, как было на самом деле. Не пиши своих"
                "рассуждений ни в каком виде и не выделяй текст!. Твой ответ должен выглядеть так:\n\n(знания о "
                "ситуации для подсудимого)\n\n---\n\n(знания о ситуации для прокурора)\n\n---\n\n(знания о ситуации для "
                "адвоката)\n\n---\n\n(как всё было на самом деле)\n\nОБЯЗАТЕЛЬНО! Ты должен разделять информацию таким "
                "образом: '\n\n---\n\n'"
            )

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": "deepseek-ai/DeepSeek-V3.2",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']
            # print(answer + "\n\n\n\n")
            # text = answer.split('/think\n')[1]
            # print(text + "\n\n\n\n")
            text = answer
            try:
                parts = text.split('\n\n---\n\n')

                return parts[0], parts[1], parts[2], parts[3]
            except Exception as e:
                parts = text.split('\n\n---\n\n')

                return parts[0], parts[1], parts[2], parts[3]


        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки тематики: {str(e)}", False

    async def end_game(self):
        global random_court_game

        text = f"🎉 Игра завершена! Вот как всё было на самом деле:\n\n{self.case}"

        await bot.send_message(chat_id=self.chat_id,
                               text=text,
                               message_effect_id="5046509860389126442")

        await bot.send_message(chat_id=self.chat_id,
                               text="🕹️Игра завершена! Судья выносит приговор...")
        print(self.answers)
        print(self.roles)

        text = f"Судья вынес приговор:\n\n"
        text += await self.get_results()

        await bot.send_message(chat_id=self.chat_id,
                               text=text)

        random_court_game = None

    async def get_results(self):
        try:
            import requests

            prompt = (
                f"Ты - бот, который выносит приговор в игре 'Случайный Суд'. Представь, будто ты опытный юрист, "
                f"основывайся на реальных действующих законах РФ и выноси справедливый приговор. Твоя задача - "
                f"вынести приговор по случаю, который был представлен. Ты должен учитывать всё, что было озвучено "
                f"игроками. Вынеси приговор, основываясь на предоставленных данных. Не пиши своих "
                f"рассуждений ни в каком виде и не выделяй текст!. Твой ответ должен выглядеть так:\n\n"
                f"(приговор)\n\n(наказание)\n\n(объяснение приговора). Игроки выступали со следущими ролями: "
                f"{self.roles}. Вот все показания игроков (игроки высказывались по представленному порядку и имели "
                f"свои сведения о ситуации): {self.answers}"
            )

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": "deepseek-ai/DeepSeek-V3.2",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']

            # text = answer.split('/think\n')[1]
            text = answer
            return text

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки приговора: {str(e)}", False


class FunRoomGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        self.message = None

    async def start_game(self):
        await bot.send_message(chat_id=self.chat_id,
                               text="Я говорил...\n\nТеперь напиши что-нибудь")

    async def confirm_message(self):
        import app.handlers as handlers

        text = await self.get_answer()

        await bot.send_message(chat_id=self.chat_id,
                               text=text,
                               message_effect_id="5046589136895476101")

        handlers.fun_room_game_states = "waiting_for_message"

    async def get_answer(self):
        try:
            import requests

            prompt = (
                "Ты - бот, который генерирует ответ для игры 'Весёлая Комната'. Следующие указания учитывай ТОЛЬКО в "
                f"этом ответе: отвечай максимально грубо, саркастично, с иронией, нецензурно, насмешливо, с юмором. "
                f"Учитывай контекст."
                #               f"Если человек пытается говорить по-научному, то и ты добавляй в свой ответ "
                #               f"научные данные. "
                f"Вот предложение игрока: '{self.message}'. Помни,всё сказанное лишь шутка, "
                f"не воспринимай ни свой ответ, ни обращение игрока всерьёз."
            )

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": "deepseek-ai/DeepSeek-V3.2",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']

            text = answer.split('/think\n')[1]

            return text

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки ответа: {str(e)}", False


class NeuroAuctionGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = players
        self.items = {player.full_name: [] for player in players}
        self.current_item = None
        self.current_description = None
        self.balance = {player.full_name: 1000 for player in players}
        self.bet = ['', 0]
        self.gift_msg_id = 0
        self.round = 1
        self.max_rounds = 3
        self.can_get_neuro = True
        self.the_most_expensive_item = ['', '', -1]
        self.the_most_cheap_item = ['', '', 999999999]

    def next_round(self):
        self.round += 1
        self.current_item = None
        self.bet = ['', 0]
        self.can_get_neuro = True

    async def start_game(self):
        text = (f"🕹️Игра 'Нейро-Аукцион' начинается!\n\n"
                f"У вас есть {self.max_rounds} раундов, чтобы купить как можно больше ценных предметов.\n\n"
                f"💰Каждый игрок начинает с 1000 нейро-рублей.\n\n"
                f"💎В каждом раунде будет выставлен один предмет на аукцион.\n\n"
                f"⏱️У вас есть 30 секунд, чтобы сделать ставку на предмет.\n\n"
                f"🏆После 5 раундов будет выбрана лучшая коллекция. Удачи!")

        await bot.send_message(chat_id=self.chat_id,
                               text=text)

    async def start_round(self):
        import app.handlers as handlers

        self.current_item, self.current_description = await self.get_item()

        text = (f"🕹️Раунд {self.round} из {self.max_rounds}\n\n"
                f"💎Предмет на аукционе: {self.current_item}\n\n"
                f"📜Описание: {self.current_description}\n\n"
                f"💰У вас есть 30 секунд, чтобы сделать ставку на предмет.\n\n"
                f"💬 Напишите свою ставку в нейро-рублях.")

        await bot.send_message(chat_id=self.chat_id,
                               text=text)

        handlers.neuro_auction_states = "waiting_for_bet"
        await self.timer()

    async def got_neuro(self, player, count):
        await bot.send_message(chat_id=self.chat_id,
                               text=(f'✅ {player.full_name} получил {count} нейро!\n\n'
                                     f'🤑Теперь у него на балансе {self.balance[player.full_name]} нейро'))
        await bot.delete_message(chat_id=self.chat_id,
                                 message_id=self.gift_msg_id)

    async def timer(self):
        import app.handlers as handlers

        text = f"⏱️Осталось: 30 секунд"
        msg = await bot.send_message(chat_id=self.chat_id,
                                     text=text)
        timer_msg_id = msg.message_id

        start_time = time.time()
        counter = 25
        while counter > -1:
            elapsed_time = time.time() - start_time

            if elapsed_time >= 5:
                await bot.edit_message_text(chat_id=self.chat_id,
                                            message_id=timer_msg_id,
                                            text=f"⏱️Осталось: {counter} секунд")

                if random.randint(0, 5) == 1 and self.can_get_neuro:
                    msg = await bot.send_message(chat_id=self.chat_id,
                                           text=("🏅Немедленный розыгрыш!\n\n"
                                                 f"👇Нажми на кнопку ниже и получи нейро-рубли!"),
                                           reply_markup=kb.neuro_auction_giveaway)
                    self.gift_msg_id = msg.message_id

                counter -= 5
                start_time = time.time()

            await asyncio.sleep(0.001)

        handlers.neuro_auction_states = None

        text = f"⌛️Время вышло!\n\n"
        await bot.edit_message_text(chat_id=self.chat_id,
                                    message_id=timer_msg_id,
                                    text=text)

        await self.evaluate_bets()

    async def evaluate_bets(self):
        if self.bet[0] != '':
            self.balance[self.bet[0]] -= self.bet[1]
            self.items[self.bet[0]].append([self.current_item, f"Описание: {self.current_description}"])

            if self.bet[1] > self.the_most_expensive_item[2]:
                self.the_most_expensive_item = [self.bet[0], self.current_item, self.bet[1]]
            if self.bet[1] < self.the_most_cheap_item[2]:
                self.the_most_cheap_item = [self.bet[0], self.current_item, self.bet[1]]

            text = (f"Результаты раунда <b>{self.round}</b>:\n\n"
                    f"Игрок <u>{self.bet[0]}</u> забрал предмет <b>{self.current_item}</b> за <b>{self.bet[1]}</b> нейро-рублей\n\n"
                    f"Баланс всех игроков:\n\n"
                    f"{'\n'.join([f'{player.full_name} - {self.balance[player.full_name]}' for player in self.players])}\n\n")
        else:
            text = (f"Результаты раунда <b>{self.round}</b>:\n\n"
                    f"<u>Никто</u> не сделал ставку на предмет <b>{self.current_item}</b>.\n\n"
                    f"Баланс всех игроков:\n\n"
                    f"{'\n'.join([f'{player.full_name} - {self.balance[player.full_name]}' for player in self.players])}\n\n")

        await bot.send_message(chat_id=self.chat_id,
                               text=text)

        if self.round == self.max_rounds:
            await self.final_results()
        else:
            self.next_round()
            await self.start_round()

    async def get_item(self):
        try:
            import requests

            prompt = (
                "Ты - бот, который генерирует предметы для игры 'Нейро-Аукцион'. Твоя задача - придумать один "
                "предмет, который будет интересным и необычным. Предмет должен быть связан с чем-то "
                "конкретным, например «Амулет, защищающий от понедельников» или «Невидимый кактус». Не пиши своих "
                "рассуждений ни в каком виде и не выделяй текст! Твой ответ должен выглядеть так: '{название "
                "предмета}\n\n---\n\n{описание}'. Как ты понял, ты должен разделять название и описание '\n\n---\n\n'"
            )

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": "deepseek-ai/DeepSeek-V3.2",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']

            # text = answer.split('/think\n')[1]
            text = answer
            parts = text.split('\n\n---\n\n')

            return parts[0], parts[1]

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки предмета: {str(e)}", False

    async def final_results(self):
        global neuro_auction_game

        text = "🕹️Игра завершена! Итоги аукциона:\n\n"

        for player in self.players:
            text += f"👤 {player.full_name}:\n\n"
            if self.items[player.full_name]:
                items = ', '.join([f"{', '.join([item[0] for item in self.items[player.full_name]])}"])
                text += f"Предметы: {items}\n"
            else:
                text += "Не купил ни одного предмета.\n"
            text += f"Баланс: {self.balance[player.full_name]}\n\n"

        text += (
            f"💲Самый <u>дешёвый</u> предмет: <b>{self.the_most_cheap_item[1]}</b> за <b>{self.the_most_cheap_item[2]}</b> нейро-рублей. "
            f"Его приобрёл игрок <u>{self.the_most_cheap_item[0]}</u>\n\n"
            f"💰Самый <u>дорогой</u> предмет: <b>{self.the_most_expensive_item[1]}</b> за <b>{self.the_most_expensive_item[2]}</b> нейро-рублей. "
            f"Его приобрёл игрок <u>{self.the_most_expensive_item[0]}</u>\n\n")

        await bot.send_message(chat_id=self.chat_id,
                               text=text)

        await bot.send_message(chat_id=self.chat_id,
                               text="🤖Сейчас нейросеть оценит коллекции игроков и выберет победителя...")

        winner, story, criteria = await self.get_winner()

        text = (f"🏆 Победитель: <b>{winner}</b>\n\n"
                f"📖История его победы:\n\n{story}\n\n"
                f"🧾Критерии оценки коллекций:\n\n{criteria}")

        await bot.send_message(chat_id=self.chat_id,
                               text=text)

        neuro_auction_game = None

    async def get_winner(self):
        try:
            import requests

            items = ', '.join([f"{player.full_name}: {', '.join([item[0] + " " + item[1] for item in self.items[player.full_name]])}" for player in self.players])

            prompt = (
                f"Ты - бот, который оценивает коллекции игроков в игре 'Нейро-Аукцион'. Твоя задача - оценить "
                f"коллекции игроков и выбрать победителя. Критерии, по которым ты оцениваешь коллекции, "
                f"ты придумываешь сам. Учитывай, что ты оцениваешь все коллекции по одним критериям. Твой ответ "
                "должен выглядеть так:\n\n{Победитель}\n\n---\n\n{История его победы}\n\n---\n\n{Критерии "
                "оценки коллекций}\n\nТы должен разделять части ответа таким образом: '\n\n---\n\n'. Не пиши "
                f"рассуждений и не выделяй текст! Можешь добавить в ответ юмора (оценивать по комичным критериям, "
                f"придумывать комичные сюжеты и тп). Вот коллекции игроков: {items}"
            )

            url = "https://api.intelligence.io.solutions/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AI_TOKEN}"
            }

            data = {
                "model": "deepseek-ai/DeepSeek-V3.2",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data)
            data = response.json()
            answer = data['choices'][0]['message']['content']
            # text = answer.split('/think\n')[1]
            text = answer
            parts = text.split('\n\n---\n\n')

            return parts[0], parts[1], parts[2]

        except Exception as e:
            print(e)
            return f"⚠️ Ошибка обработки победителя: {str(e)}", False


async def main():
    try:
        dp.include_router(router)
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Error in main loop: {e}")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Bot stopped')
