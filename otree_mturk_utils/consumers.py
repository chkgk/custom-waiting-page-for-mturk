from .models import Mturk, WPJobRecord, ROWS, BigFiveData
from random import randint
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from importlib import import_module
import json


class CustomWaitPageConsumer(WebsocketConsumer):
    def _get_models_module(self, app_name):
        module_name = '{}.models'.format(app_name)
        return import_module(module_name)

    # ============= For creating a task
    def _slicelist(self, l, n):
        return [l[i:i + n] for i in range(0, len(l), n)]

    def _get_random_list(self):
        max_len = 100
        low_upper_bound = 50
        high_upper_bound = 99
        return [randint(10, randint(low_upper_bound, high_upper_bound)) for i in range(max_len)]

    def get_task(self):
        string_len = 10
        listx = self._get_random_list()
        listy = self._get_random_list()
        answer = max(listx) + max(listy)
        listx = self._slicelist(listx, string_len)
        listy = self._slicelist(listy, string_len)
        return {
            "message_type": "new_task",
            "mat1": listx,
            "mat2": listy,
            "correct_answer": answer,
        }

    def update_state(self, app_name, group_pk, gbat, index_in_pages):
        those_with_us = self._get_models_module(app_name).Player.objects.filter(
            group__pk=group_pk,
            participant__mturk__current_wp=index_in_pages,
        )
        how_many_arrived = len(those_with_us)
        print('HOW MANY ARRIVED:', how_many_arrived)
        players_per_group = self._get_models_module(app_name).Constants.players_per_group

        left_to_wait = players_per_group - how_many_arrived

        textforgroup = json.dumps({
            "message_type": "players_update",
            "how_many_arrived": how_many_arrived,
            "left_to_wait": left_to_wait,
        })

        async_to_sync(self.channel_layer.group_send)(
            'group_{}_{}'.format(app_name, group_pk),
            {
                "text": textforgroup
            }
        )

    def connect(self):
        message = self.scope['url_route']['kwargs']['message']
        participant_code = self.scope['url_route']['kwargs']['participant_code']
        app_name = self.scope['url_route']['kwargs']['app_name']
        group_pk = self.scope['url_route']['kwargs']['group_pk']
        player_pk = self.scope['url_route']['kwargs']['player_pk']
        index_in_pages = self.scope['url_route']['kwargs']['index_in_pages']
        gbat = self.scope['url_route']['kwargs']['gbat']

        print('somebody connected from custom wp..')
        try:
            mturker = Mturk.objects.get(Participant__code=participant_code)
        except ObjectDoesNotExist:
            return None

        mturker.current_wp = index_in_pages
        mturker.save()
        new_task = get_task()
        wprecord, created = mturker.wpjobrecord_set.get_or_create(app=app_name, page_index=index_in_pages)
        wprecord.last_correct_answer = new_task['correct_answer']
        wprecord.save()
        new_task['tasks_correct'] = wprecord.tasks_correct
        new_task['tasks_attempted'] = wprecord.tasks_attempted
        self.send({'text': json.dumps(new_task)})

        async_to_sync(self.channel_layer.group_add)(
            'group_{}_{}'.format(app_name, group_pk),
            self.channel_name
        )
        self.update_state(app_name, group_pk, gbat, index_in_pages)

    
    def receive(self, text_data):
        participant_code = self.scope['url_route']['kwargs']['participant_code']
        app_name = self.scope['url_route']['kwargs']['app_name']
        group_pk = self.scope['url_route']['kwargs']['group_pk']
        player_pk = self.scope['url_route']['kwargs']['player_pk']
        index_in_pages = self.scope['url_route']['kwargs']['index_in_pages']
        gbat = self.scope['url_route']['kwargs']['gbat']
    
        jsonmessage = json.loads(text_data.content['text'])
        answer = jsonmessage.get('answer')
    
        if answer:
            with transaction.atomic():
                try:
                    mturker = Mturk.objects.select_for_update().get(Participant__code=participant_code)
                    wprecord = WPJobRecord.objects.get(mturker=mturker,
                                                       page_index=index_in_pages,
                                                       app=app_name)
                except ObjectDoesNotExist:
                    return None
    
                wprecord.tasks_attempted += 1
    
                if int(answer) == int(wprecord.last_correct_answer):
                    wprecord.tasks_correct += 1
    
                new_task = get_task()
                new_task['tasks_correct'] = wprecord.tasks_correct
                new_task['tasks_attempted'] = wprecord.tasks_attempted
                wprecord.last_correct_answer = new_task['correct_answer']
                wprecord.save()
    
            self.send({'text': json.dumps(new_task)})

    # Connected to websocket.disconnect
    def disconnect(self, close_code):
        message = self.scope['url_route']['kwargs']['message']
        participant_code = self.scope['url_route']['kwargs']['participant_code']
        app_name = self.scope['url_route']['kwargs']['app_name']
        group_pk = self.scope['url_route']['kwargs']['group_pk']
        player_pk = self.scope['url_route']['kwargs']['player_pk']
        index_in_pages = self.scope['url_route']['kwargs']['index_in_pages']
        gbat = self.scope['url_route']['kwargs']['gbat']
        try:
            mturker = Mturk.objects.get(Participant__code=participant_code)
        except ObjectDoesNotExist:
            return None

        mturker.current_wp = None
        mturker.save()
        print('somebody disconnected...')
        async_to_sync(self.channel_layer.group_discard)(
            'group_{}_{}'.format(app_name, group_pk),
            self.channel_name
        )

        self.update_state(app_name, group_pk, gbat, index_in_pages)


class BigFiveConsumer(WebsocketConsumer):
    def connect(self):
        print('connected')

    def receive(self, text_data):
        participant_code = self.scope['url_route']['kwargs']['participant_code']
        jsonmessage = json.loads(text_data.content['text'])
        print("json:::", jsonmessage)

        dictionary = jsonmessage['answers']
        answer_vector = []
        num_questions = len(ROWS)
        for i in range(0, num_questions):
            try:
                answer_vector.append(dictionary[str(i)])
            except KeyError:
                answer_vector.append("0")

        data, created = BigFiveData.objects.get_or_create(Participant__code=participant_code)
        data.bigfive = answer_vector
        data.save()
        print("bigfive::::", data.bigfive)

    def disconnect(self, close_code):
        print('disconnected')
