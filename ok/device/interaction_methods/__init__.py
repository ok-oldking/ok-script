from ok.device.interaction_methods.adb import ADBInteraction
from ok.device.interaction_methods.base import BaseInteraction
from ok.device.interaction_methods.browser import BrowserInteraction
from ok.device.interaction_methods.do_nothing import DoNothingInteraction
from ok.device.interaction_methods.foreground_post_message import ForegroundPostMessageInteraction
from ok.device.interaction_methods.genshin import GenshinInteraction, INPUT, MOUSEINPUT, SendInput
from ok.device.interaction_methods.keys import ADB_KEY_MAP, PYDIRECT_KEY_MAP, normalize_pydirect_key, vk_key_dict
from ok.device.interaction_methods.post_message import PostMessageInteraction
from ok.device.interaction_methods.pydirect import PyDirectInteraction
from ok.device.interaction_methods.pynput import PynputInteraction
from ok.device.interaction_methods.swipe import insert_swipe
