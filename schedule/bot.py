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
from typing import List
from flask import Flask, request, Response
from threading import Thread


app = Flask("")

_mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG


def dict_representer(dumper, data):
    return dumper.represent_dict(data.iteritems())


def dict_constructor(loader, node):
    return OrderedDict(loader.construct_pairs(node))


Dumper.add_representer(OrderedDict, dict_representer)
Loader.add_constructor(_mapping_tag, dict_constructor)

Dumper.add_representer(str, SafeRepresenter.represent_str)

alarm_hour = 3

current_year = 2022

dateformat = "%Y-%m-%d %H:%M"
tba_words = ["tba", "tbd"]
subfield2fullname = {
    "CV": "Computer Vision",
    "CG": "Computer Graphics",
    "ML": "Machine Learning",
    "RO": "Robotics",
    "NLP": "Natural Language Processing",
    "SP": "Speech/SigProcessing",
    "DM": "Data Mining",
}


def get_now(kst=False):
    if kst:
        return (
            datetime.datetime.utcnow()
            .replace(tzinfo=pytz.timezone("UTC")).replace(microsecond=0)
            .astimezone(pytz.timezone("Asia/Seoul")).strftime(dateformat)
        )
    return datetime.datetime.utcnow().replace(microsecond=0).strftime(dateformat)


def invert_dictionary(dic):
    dict2 = dict()
    for k, v in dic.items():
        dict2[v] = k
    return dict2


class Calendar:
    def __init__(self, yml_path):
        self.yml_path = yml_path

        with open(yml_path, "r") as stream:
            data = yaml.load(stream, Loader=Loader)
        data = self.fix_data(data)

        conf = [x for x in data if str(x["deadline"]).lower() not in tba_words]
        tba = [x for x in data if str(x["deadline"]).lower() in tba_words]

        right_now = get_now()
        # sorting
        conf.sort(
            key=lambda x: pytz.utc.normalize(
                datetime.datetime.strptime(x["deadline"], dateformat).replace(
                    tzinfo=pytz.timezone(x["timezone"])
                )
            )
        )
        # clear past conferences
        conf_remaining = []
        for q in conf:
            if q["deadline"] > right_now:
                conf_remaining.append(q)

        # to KST
        for q in conf_remaining:
            original_date = datetime.datetime.strptime(
                q["deadline"], dateformat
            ).replace(tzinfo=pytz.timezone(q["timezone"]))
            kst_tz = pytz.timezone("Asia/Seoul")
            kst_date = original_date.astimezone(kst_tz)
            q["kst_deadline"] = kst_date.strftime(dateformat)

            if q.get("abstract_deadline"):
                original_date = datetime.datetime.strptime(
                    q["abstract_deadline"], dateformat
                ).replace(tzinfo=pytz.timezone(q["timezone"]))
                kst_date = original_date.astimezone(kst_tz)
                q["kst_abstract_deadline"] = kst_date.strftime(dateformat)

        self.conf = conf_remaining
        self.tba = tba

    def conference_info_message(self, q):
        today = get_now()
        title = q["title"]
        subfield = q["sub"]
        deadline = q["deadline"]
        day_diff = datetime.datetime.strptime(
            deadline, dateformat
        ) - datetime.datetime.strptime(today, dateformat)
        d_day = day_diff.days
        seconds = day_diff.seconds
        remaining_hours = seconds // 3600
        remaining_minutes = (seconds - remaining_hours * 3600) // 60
        if d_day == 0:
            d_day_msg = f"D-0 {remaining_hours}:{remaining_minutes}"
        else:
            d_day_msg = f"D-{d_day}"

        timezone = q["timezone"]
        place = q["place"]

        msg = f"*[{title}]* {subfield2fullname[subfield]}\n"
        msg += f"- Deadline: *{d_day_msg}*. {deadline.replace(str(current_year)+'-', '').replace('-', '/')} ({timezone})\n"

        if q.get("abstract_deadline"):
            msg += f"- Abstract Deadline: {q['abstract_deadline'].replace(str(current_year)+'-', '').replace('-', '/')}\n"
        msg += f"- Place: {place}\n\n"

        return msg

    def conference_info_message_kst(self, q):
        today = get_now(kst=True)

        title = q["title"]
        subfield = q["sub"]
        deadline = q["kst_deadline"]
        day_diff = datetime.datetime.strptime(
            deadline, dateformat
        ) - datetime.datetime.strptime(today, dateformat)
        d_day = day_diff.days
        seconds = day_diff.seconds
        remaining_hours = seconds // 3600
        remaining_minutes = (seconds - remaining_hours * 3600) // 60
        if d_day == 0:
            d_day_msg = f"D-0 {remaining_hours}:{remaining_minutes}"
        else:
            d_day_msg = f"D-{d_day}"

        timezone = "KST"
        place = q["place"]

        msg = f"*[{title}]* {subfield2fullname[subfield]}\n"
        msg += f"- Deadline: *{d_day_msg}*. {deadline.replace('2022-', '').replace('-', '/')} ({timezone})\n"

        if q.get("kst_abstract_deadline"):
            msg += f"- Abstract Deadline: {q['kst_abstract_deadline'].replace('2022-', '').replace('-', '/')}\n"
        msg += f"- Place: {place}\n\n"

        return msg

    def padding_time(self, strtime):
        num_parser = len(strtime.split(":"))
        if num_parser == 3:
            return strtime[:-3]
        elif num_parser == 2:
            return strtime
        else:
            raise ValueError

    def fix_data(self, data):
        for x in data:
            x["deadline"] = self.padding_time(x["deadline"])
            if x.get("abstract_deadline"):
                x["abstract_deadline"] = self.padding_time(x["abstract_deadline"])
            x["timezone"] = (
                x["timezone"]
                .replace("UTC+", "Etc/GMT-")
                .replace("UTC-", "Etc/GMT+")
                .replace("PDT", "America/Los_Angeles")
            )
        return data


class SlackBot:
    def __init__(self, token):
        self.client = WebClient(token)
        self.calendar = Calendar("./ai-deadlines/_data/conferences.yml")

        # self.register_memeber_list()

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
            self.members.append(
                {"user_id": user_id, "name": name, "real_name": real_name}
            )
            self.id2name[user_id] = name
            self.id2real_name[user_id] = real_name
            self.name2id = invert_dictionary(self.id2name)
            self.real_name2id = invert_dictionary(self.id2real_name)

    def get_deadlines(self, interesting_confs, subfields: List = ["CV", "CG", "ML"]):
        """
        subfileds: [
        "ML":Machline Learning,
        "CV": Computer Vision,
        "CG": Computer Graphics,
        "NLP": Natural Language Processing,
        "RO": Robotics,
        "SP": Speech/SigProcessing,
        "DM": Data Mining
        ]
        """
        kst_today = get_now(kst=True)
        msg = f"Good morning! :wave: Today is *{kst_today[:10].replace(str(current_year)+'-', '').replace('-', '/')}*\n"
        if interesting_confs is not None:

            for q in self.calendar.conf:
                if q["title"] in interesting_confs:
                    msg += self.calendar.conference_info_message_kst(q)
                    # msg += self.calendar.conference_info_message_kst(q)
        else:
            for q in self.calendar.conf:
                if q["sub"] in subfields:
                    msg += self.calendar.conference_info_message_kst(q)
                    # msg += self.calendar.conference_info_message(q)

        return msg

    def send_dm(self, name, msg):
        user_id = self.name2id[name]
        self.client.chat_postMessage(channel=user_id, text=msg)

    def post_message(self, channel_name, msg):
        channel_id = self.get_channel_id(channel_name)
        self.client.chat_postMessage(channel=channel_id, text=msg)

    @app.route("/deadlines", methods=["POST"])
    def hello_slash():
        pass
        # query_word = request.form['text']
        # user = request.form['user_id']
        # ts = ''
        # answer = get_answer(query_word, user, ts)

        # return make_response(answer, 200, {"content_type": "application/json"})


def main():
    env_path = Path("../") / ".env"
    load_dotenv(env_path)

    slack = SlackBot(os.environ["SLACK_TOKEN"])
    
    while True:
        nowtime = time.localtime()
        if nowtime.tm_hour == alarm_hour:

            deadlines = slack.get_deadlines(["ICLR", "CVPR", "ICCV"])
            slack.post_message("deadlines", deadlines)
            print(deadlines)
        
        time.sleep(3600)



if __name__ == "__main__":
    main()
