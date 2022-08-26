from slack_sdk import WebClient
from collections import OrderedDict
import time
import time
from pathlib import Path
from dotenv import load_dotenv
import os
import yaml
import datetime
import pytz
from yaml import CLoader as Loader, CDumper as Dumper
from yaml.representer import SafeRepresenter
_mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG
def dict_representer(dumper, data):
    return dumper.represent_dict(data.iteritems())


def dict_constructor(loader, node):
    return OrderedDict(loader.construct_pairs(node))


Dumper.add_representer(OrderedDict, dict_representer)
Loader.add_constructor(_mapping_tag, dict_constructor)

Dumper.add_representer(str, SafeRepresenter.represent_str)


def invert_dictionary(dic):
    dict2 = dict()
    for k, v in dic.items():
        dict2[v] = k
    return dict2

dateformat = "%Y-%m-%d %H:%M:%S"
tba_words = ["tba", "tbd"]

right_now = datetime.datetime.utcnow().replace(microsecond=0).strftime(dateformat)

def load_yaml(filename):
    with open(filename, "r") as stream:
        # try:
        data = yaml.load(stream, Loader=Loader)
    return data 

            # print("Initial Sorting:")
            # for q in data:
                # print(q["deadline"], " - ", q["title"])
            # print("\n\n")
            # conf = [x for x in data if str(x['deadline']).lower() not in tba_words]
            # tba = [x for x in data if str(x['deadline']).lower() in tba_words]

            # # just sort:
            # conf.sort(key=lambda x: pytz.utc.normalize(datetime.datetime.strptime(x['deadline'], dateformat).replace(tzinfo=pytz.timezone(x['timezone'].replace('UTC+', 'Etc/GMT-').replace('UTC-', 'Etc/GMT+').replace("PDT", "America/Los_Angeles")))))
            # print("Date Sorting:")
            # for q in conf + tba:
                # print(q["deadline"], " - ", q["title"])
            # print("\n\n")
            # conf.sort(key=lambda x: pytz.utc.normalize(datetime.datetime.strptime(x['deadline'], dateformat).replace(tzinfo=pytz.timezone(x['timezone'].replace('UTC+', 'Etc/GMT-').replace('UTC-', 'Etc/GMT+').replace("PDT", "America/Los_Angeles")))).strftime(dateformat) < right_now)
            # print("Date and Passed Deadline Sorting with tba:")
            # for q in conf + tba:
                # print(q["deadline"], " - ", q["title"])
            # print("\n\n")
        # except yaml.YAMLError as exc:
            # print(exc)

class SlackBot:
    def __init__(self, token):
        self.client = WebClient(token)
        self.register_memeber_list()
        self.conference_data = load_yaml("./ai-deadlines/_data/conferences.yml")

    def get_channel_id(self, channel_name):
        result = self.client.conversations_list()
        channels = result.data["channels"]
        channel = list(filter(lambda c: c["name"] == channel_name, channels))[0]

        channel_id = channel["id"]

        return channel_id
    
    def register_memeber_list(self):
        channel_id = self.get_channel_id("gpu-overheat")
        user_ids = self.client.conversations_members(channel=channel_id)["members"]
        
        self.members = []
        self.id2name = dict()
        self.id2real_name = dict()
        for user_id in user_ids:
            info = self.client.users_info(user=user_id)["user"]
            name = info["name"]
            real_name = info["real_name"]
            self.members.append({"user_id": user_id, "name": name, "real_name": real_name})
            self.id2name[user_id] = name
            self.id2real_name[user_id] = real_name
            self.name2id = invert_dictionary(self.id2name)
            self.real_name2id = invert_dictionary(self.id2real_name)

    def send_message(self, name):
        user_id = self.name2id[name]
        msg = ""
        for q in self.conference_data:
            msg += f"{q['deadline']}({q['timezone']}) - {q['title']}\n"
        self.client.chat_postMessage(channel=user_id, text=msg)

def main():
    env_path = Path("../") / ".env"
    load_dotenv(env_path)

    slack = SlackBot(os.environ["SLACK_TOKEN"])
    slack.send_message("63days")
    # slack.register_memeber_list()
    # print(slack.name2id)
    
    # juil_id = slack.name2id["63days"]
    # slack.client.chat_postMessage(channel=juil_id, text="hi")
if __name__ == "__main__":
    main()
