import traceback
import uuid
from typing import Optional, Literal

import flet as ft
import openai
from loguru import logger


async def snack_bar(page, message):
    page.snack_bar = ft.SnackBar(content=ft.Text(message), action="好的")
    page.snack_bar.open = True
    await page.update_async()
    logger.info(f"snack bar message {message}")


class Openai:
    def __init__(self):
        self.openai = openai
        self.conversations = []

    async def send(self, model, api_key, message):
        # proxy = await get_proxy()
        # self.openai.proxy = proxy
        if not self.openai.api_key:
            self.openai.api_key = api_key
        tmp = self.conversations + [{"role": "user", "content": message}]
        response = await self.openai.ChatCompletion.acreate(
            model=model,
            messages=tmp,
            stream=True,  # this time, we set stream=True
            # timeout=20,
            # request_timeout=20
        )
        res = {"role": "assistant", "content": ""}
        try:
            async for chunk in response:
                delta = chunk.choices[0]["delta"]
                if "role" in delta:
                    res["role"] = delta["role"]
                if "content" in delta:
                    res["content"] += delta["content"]
                    yield delta["content"]
        except TimeoutError as e:
            logger.info(f"openai timeout {e}")
        self.conversations.append({"role": "user", "content": message})
        self.conversations.append(res)

    def reset(self):
        self.conversations.clear()


class Message(ft.UserControl):
    def __init__(
        self,
        root: "ViewPage",
        parent: "Conversation",
        role: Literal["user", "assistant"],
        source_text="",
    ):
        self.root = root
        self.parent = parent
        self.role = role
        super().__init__()
        self.avatar: Optional[ft.CircleAvatar] = None
        self.text: Optional[ft.Text] = None
        self.copy_btn: Optional[ft.TextButton] = None
        self.message: Optional[ft.Markdown] = None
        self.source_text = source_text
        self.ui: Optional[ft.Row] = None

    def build(self):
        if self.role == "user":
            self.avatar = ft.CircleAvatar(
                content=ft.Icon(
                    name=ft.icons.ACCOUNT_CIRCLE_ROUNDED,
                    size=16,
                ),
                width=30,
                height=30,
            )
            self.text = ft.Text("用户")
        else:
            self.avatar = ft.CircleAvatar(
                content=ft.Icon(name=ft.icons.KEYBOARD_COMMAND_KEY_OUTLINED, size=16),
                width=30,
                height=30,
            )
            self.text = ft.Text("GPT")
        self.copy_btn = ft.TextButton("copy", on_click=self.copy_action)
        self.message = ft.Markdown(
            "",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            on_tap_link=self.launch_url,
        )
        self.source_text = ft.Text(self.source_text)
        self.ui = ft.Row(
            [
                ft.Row(
                    [
                        ft.Row([self.avatar, self.text]),
                        ft.Row([self.source_text, self.copy_btn]),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(self.message, padding=ft.Padding(10, 0, 0, 10)),
                # ft.Column([self.avatar]),
                # ft.Column(
                #     [ft.Container(self.message, padding=ft.Padding(100, 10, 5, 5))],
                #     auto_scroll=True,
                # ),
                ft.Divider(),
            ],
            # vertical_alignment=ft.CrossAxisAlignment.START,
            wrap=True,
        )
        return self.ui

    async def add_message(self, text):
        self.message.value += text
        await self.update_async()

    async def new_message(self, text):
        self.message.value = text
        await self.update_async()

    async def copy_action(self, e=None):
        await self.page.set_clipboard_async(self.message.value)
        # await snack_bar(self.page, f"已复制 {self.message.value}")
        await self.parent.prompt_input.focus_async()

    async def launch_url(self, e):
        await self.page.launch_url_async(e.data)


class Conversation(ft.UserControl):
    def __init__(self, root: "ViewPage", parent):
        self.root = root
        self.parent = parent
        super().__init__(expand=1)
        self.chat_area: Optional[ft.ListView] = None
        self.prompt_input: Optional[ft.TextField] = None
        self.send_btn: Optional[ft.FloatingActionButton] = None
        self.ui: Optional[ft.Column] = None

    def build(self):
        self.chat_area = ft.ListView(
            expand=True,
            spacing=10,
            auto_scroll=True,
        )
        self.prompt_input = ft.TextField(on_submit=self.send, expand=1, autofocus=True)
        self.send_btn = ft.FloatingActionButton("发送", on_click=self.send, width=150)
        self.ui = ft.Column(
            [ft.Divider(), self.chat_area, ft.Row([self.prompt_input, self.send_btn])]
        )
        return self.ui

    async def did_mount_async(self):
        self.chat_area.controls.append(ft.Text(""))

    async def send(self, e=None):
        if not self.prompt_input.value:
            return
        text = self.prompt_input.value
        self.prompt_input.value = ""
        await self.show_message(text, "user")
        await self.update_async()
        await self.parent.send_message(text)
        await self.prompt_input.focus_async()

    async def show_message(self, text, role):
        __c = self.chat_area.controls
        if __c:
            __c.pop(-1)
        if not __c or __c[-1].role != role:
            message = Message(
                self.parent,
                self,
                role,
                source_text=self.parent.api.name if hasattr(self.parent, "api") else "",
            )
            self.chat_area.controls.append(message)
            await self.update_async()
        else:
            message = __c[-1]
        await message.add_message(text)
        self.chat_area.controls.append(ft.Text(""))
        await self.update_async()

    async def clear_messages(self):
        self.chat_area.controls.clear()
        await self.update_async()


class SettingDialog(ft.UserControl):
    def __init__(self, root: "ViewPage", parent):
        self.root = root
        self.parent = parent
        super().__init__()
        self.click_btn: Optional[ft.IconButton] = None
        self.api_key_input: Optional[ft.TextField] = None
        self.model_select: Optional[ft.Dropdown] = None
        self.cancel_btn: Optional[ft.IconButton] = None
        self.save_btn: Optional[ft.IconButton] = None

    def build(self):
        self.click_btn = ft.IconButton(
            icon=ft.icons.SETTINGS_OUTLINED, on_click=self.open_dialog
        )
        self.api_key_input = ft.TextField(label="OpenAI API 密钥")
        self.model_select = ft.Dropdown(
            label="模型",
            value="gpt-3.5-turbo",
            options=[
                ft.dropdown.Option("gpt-3.5-turbo"),
                ft.dropdown.Option("gpt-3.5-turbo-0301"),
                ft.dropdown.Option("gpt-4"),
                ft.dropdown.Option("gpt-4-0314"),
                ft.dropdown.Option("gpt-4-32k"),
                ft.dropdown.Option("gpt-4-32k-0314"),
            ],
        )
        self.cancel_btn = ft.FloatingActionButton(
            "取消", on_click=self.close_dialog, width=100
        )
        self.save_btn = ft.FloatingActionButton(
            "保存", on_click=self.save_setting, width=100
        )
        return self.click_btn

    async def did_mount_async(self):
        self.api_key_input.value = await self.page.client_storage.get_async(
            "gpt_api_key"
        )
        gpt_model = await self.page.client_storage.get_async("gpt_model")
        if gpt_model:
            self.model_select.value = gpt_model
        await self.update_async()

    async def open_dialog(self, e=None):
        await self.did_mount_async()
        if self.page.dialog:
            dialog = self.page.dialog
        else:
            dialog = ft.AlertDialog()
        dialog.title = ft.Text("GPT 设置")
        dialog.content = ft.Column([self.api_key_input, self.model_select], width=600)
        dialog.actions = [self.save_btn, self.cancel_btn]
        dialog.actions_alignment = ft.MainAxisAlignment.CENTER
        dialog.open = True
        self.page.dialog = dialog
        await self.page.update_async()

    async def close_dialog(self, e=None):
        self.page.dialog.open = False
        await self.page.update_async()

    async def save_setting(self, e=None):
        self.parent.api_key = self.api_key_input.value
        await self.page.client_storage.set_async(
            "gpt_api_key", self.api_key_input.value
        )
        self.parent.title.value = self.model_select.value
        await self.page.client_storage.set_async("gpt_model", self.model_select.value)
        await self.parent.update_async()
        await self.close_dialog()


class ViewPage(ft.UserControl):
    def __init__(self):
        super().__init__(expand=1)
        self.api_key = ""
        self.openai = Openai()
        self.title: Optional[ft.Text] = None
        self.clear_btn: Optional[ft.IconButton] = None
        self.setting_btn: Optional[SettingDialog] = None
        self.question_btn: Optional[ft.IconButton] = None
        self.conversation: Optional[Conversation] = None
        self.ui: Optional[ft.Container] = None
        self.generating_id = None

    def build(self):
        self.title: Optional[ft.Text] = ft.Text("", weight=ft.FontWeight.BOLD)
        self.clear_btn = ft.IconButton(
            icon=ft.icons.CLEANING_SERVICES_OUTLINED, on_click=self.reset_conversation
        )
        self.setting_btn = SettingDialog(self, self)
        self.question_btn = ft.IconButton(
            icon=ft.icons.QUESTION_MARK_OUTLINED,
            tooltip="""使用教程
1. 打开代理
2. 在 https://platform.openai.com/ 登录你的openai账号
3. 点击头像-View API Keys，生成secret key
4. 点击本页的设置，将 secret key添入， 并点击保存
5. 软件会自动检测代理，开始使用吧
        """,
        )
        self.conversation = Conversation(self, self)
        self.ui = ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [
                            self.title,
                            ft.Row(
                                [self.clear_btn, self.setting_btn, self.question_btn]
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.conversation,
                ]
            ),
            padding=15,
        )
        return self.ui

    async def did_mount_async(self):
        self.api_key = await self.page.client_storage.get_async("gpt_api_key")
        model = await self.page.client_storage.get_async("gpt_model") or "gpt-3.5-turbo"
        self.title.value = model
        await self.update_async()

    async def send_message(self, text):
        try:
            self.generating_id = generating_id = uuid.uuid4()
            async for word in self.openai.send(self.title.value, self.api_key, text):
                if generating_id != self.generating_id:
                    return
                await self.conversation.show_message(word, role="assistant")
        except Exception as e:
            logger.warning(f"openai send message {traceback.format_exc()}")
            await self.conversation.show_message(str(e), role="assistant")

    async def reset_conversation(self, e):
        self.generating_id = uuid.uuid4()
        await self.conversation.clear_messages()
        self.openai.reset()
        await self.conversation.prompt_input.focus_async()


async def main(page: ft.Page):
    page.title = "CHATGPT对器"
    await page.add_async(ViewPage())


if __name__ == "__main__":
    ft.app(target=main)
