from django.conf.urls import url
from otree_mturk_utils.consumers import BigFiveConsumer, CustomWaitPageConsumer

waiting_channel_name = r'^/waiting_page/(?P<participant_code>\w+)/(?P<app_name>\w+)/(?P<group_pk>\w+)/(?P<player_pk>\w+)/(?P<index_in_pages>\w+)/(?P<gbat>\w+)$'
bigfive_path = r'^/bigfive/(?P<participant_code>\w+)$'

websocket_routing = [
    url(waiting_channel_name, CustomWaitPageConsumer),
    url(bigfive_path, BigFiveConsumer)
]