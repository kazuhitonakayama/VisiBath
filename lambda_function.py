import os
import sys
# datetimeオブジェクトのインポート
from datetime import datetime
import math
# DynamoDBとの接続
import boto3, json
# 例外処理のメソッドをインポート
from botocore.exceptions import ClientError

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,PostbackEvent,PostbackTemplateAction
)
from linebot.exceptions import (
    LineBotApiError, InvalidSignatureError
)

import logging

logger = logging.getLogger()
logger.setLevel(logging.ERROR)

channel_secret = os.getenv('LINE_CHANNEL_SECRET', None) # チャンネルシークレットの定義。 「Configration」の[Environmental variables]にて環境変数化する
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None) # チャンネルのアクセストークンの定義。 「Configration」の[Environmental variables]にて環境変数化する

if channel_secret is None: # もしチャンネルシークレットの値がないならば、コードの実行を許可しない
    logger.error('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None: # もしチャンネルアクセストークンの値がないならば、コードの実行を許可しない
    logger.error('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

# ↑ここまではコードの実行権限を確認するもの。


def lambda_handler(event, context):
    # レスポンスを受ける権限をsignatureがあるかどうかで確認
    if "x-line-signature" in event["headers"]:
        signature = event["headers"]["x-line-signature"]
    elif "X-Line-Signature" in event["headers"]:
        signature = event["headers"]["X-Line-Signature"]
    
    # 送信されたメッセージを受信し、実行完了時と実行エラー時の処理を記述
    body = event["body"]
    ok_json = {"isBase64Encoded": False,
               "statusCode": 200,
               "headers": {},
               "body": ""}
    error_json = {"isBase64Encoded": False,
                  "statusCode": 500,
                  "headers": {},
                  "body": "Error"}

    try:
        handler.handle(body, signature)
    except LineBotApiError as e:
        logger.error("Got exception from LINE Messaging API: %s\n" % e.message)
        for m in e.error.details:
            logger.error("  %s: %s" % (m.property, m.message))
        return error_json
        # エラー時の処理
    except InvalidSignatureError:
        return error_json
        # エラー時の処理

    return ok_json # テキストの受信に成功すればok_jsonを返す

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event): # 引数のeventにAPIからのレスポンスが入っている
    text = event.message.text # 送信されたメッセージを取得
    returnUserid = event.source.user_id # 送信されたメッセージを取得
    line_bot_api.reply_message(event.reply_token, TextSendMessage("下のメニューから選択してね！")) # トークンと送信テキストをTextSendMessage(text)にて指定。ここではecho botのため、送信された内容と同じ内容を返すようにしている。

@handler.add(PostbackEvent)
def on_postback(event):
    # DynamoDBにデータを送信する
    dynamoDB = boto3.resource("dynamodb")
    table = dynamoDB.Table("Bath") # Bathテーブルに接続
    
    # PostBackを取得
    postback_msg = event.postback.data
    postback_user_id = event.source.user_id

    # 現在の時刻を取得
    raw_current_time = datetime.now()
    current_time = raw_current_time.isoformat(timespec='seconds')

    if postback_msg == 'f_out':
        #DynamoDBへのgetItem処理実行
        response = table.get_item(Key={'building': 1, 'gender': 1})

        # DBのtimeとcurrent_timeの差分を計測し、秒数を分に変換する
        diff_between_current_and_past = (datetime.strptime(current_time,'%Y-%m-%dT%H:%M:%S') - datetime.strptime(response['Item']['time'],'%Y-%m-%dT%H:%M:%S')).seconds
        integer_of_diff = math.floor(diff_between_current_and_past / 60)

        if response['Item']['vacancy'] == True and response['Item']['user_id'] == postback_user_id: # 誰かが入っている、かつ、それが他人でないとき(自分)のみ空室にできる
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text='お風呂を「空き」にしたよ！')
            )
            option = {
                'Key': {
                    'building': 1,
                    'gender': 1
                },
                'UpdateExpression': 'set #vacancy = :v',
                'ExpressionAttributeNames': {
                    '#vacancy': 'vacancy'
                },
                'ExpressionAttributeValues': {
                    ':v': False
                }
            }
            table.update_item(**option)
        elif response['Item']['vacancy'] == True and response['Item']['user_id'] != postback_user_id: # 誰かが入っている、かつ、それが他人のときは
            if integer_of_diff > 2700:  # 45分以上経過していたら他人の入室を空きに変更する
                option = {
                    'Key': {
                        'building': 1,
                        'gender': 1
                    },
                    'UpdateExpression': 'set #vacancy = :v',
                    'ExpressionAttributeNames': {
                        '#vacancy': 'vacancy'
                    },
                    'ExpressionAttributeValues': {
                        ':v': False
                    }
                }
                table.update_item(**option)
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='女風呂は45分以上も前から誰かが入浴中ですので空きに変更しました！お風呂に入りたいときはピンク色のinを選択してね')
                )
            else:   # 45分以上経過していないなら
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='他の人が入っているときは「out」を選択できません..！今入浴中の方は%i分前に入浴し始めました！' % (integer_of_diff))
                )
        elif response['Item']['vacancy'] == False: # 誰も入っていない時は
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text='お風呂は既に「空き」だよ！')
            )
    elif postback_msg == 'f_check':
        # DynamoDBへのgetItem処理実行
        response = table.get_item(Key={'building': 1, 'gender': 1})

        # DBのtimeとcurrent_timeの差分を計測し、秒数を分に変換する
        diff_between_current_and_past = (datetime.strptime(current_time,'%Y-%m-%dT%H:%M:%S') - datetime.strptime(response['Item']['time'],'%Y-%m-%dT%H:%M:%S')).seconds
        integer_of_diff = math.floor(diff_between_current_and_past / 60)

        if response['Item']['vacancy'] == True and response['Item']['user_id'] == postback_user_id: # もし自分が入浴中になっていたら
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text='%i分前からあなたが入浴中にしてます！' % (integer_of_diff))
            )
        elif response['Item']['vacancy'] == True and response['Item']['user_id'] != postback_user_id: # もし自分以外の誰かが入浴中になっていたら
            if integer_of_diff > 2700: # 45分以上経過していたら入室から空きに変更する
                option = {
                    'Key': {
                        'building': 1,
                        'gender': 1
                    },
                    'UpdateExpression': 'set #vacancy = :v',
                    'ExpressionAttributeNames': {
                        '#vacancy': 'vacancy'
                    },
                    'ExpressionAttributeValues': {
                        ':v': False
                    }
                }
                table.update_item(**option)
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='女風呂は45分以上も前から誰かが入浴中ですので空きに変更しました！お風呂に入りたいときはピンク色のinを選択してね')
                )
            else: # 45分以上経過していないなら入室から変更なし
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='女風呂は%i分前から誰かが入浴中です！' % (integer_of_diff))
                )
        elif response['Item']['vacancy'] == False:
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text="女風呂は誰も入浴してません！入れます！お風呂に入りたいときはピンク色のinを選択してね")
            )
    elif postback_msg == 'f_in':
        # DynamoDBへのgetItem処理実行
        response = table.get_item(Key={'building': 1, 'gender': 1})

        # DBのtimeとcurrent_timeの差分を計測し、秒数を分に変換する
        diff_between_current_and_past = (datetime.strptime(current_time,'%Y-%m-%dT%H:%M:%S') - datetime.strptime(response['Item']['time'],'%Y-%m-%dT%H:%M:%S')).seconds
        integer_of_diff = math.floor(diff_between_current_and_past / 60)

        if response['Item']['vacancy'] == True and response['Item']['user_id'] == postback_user_id: # もし誰かが入浴中かつその人が自分なら
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text='既に%i分前からあなたが「入浴中」になってます！ゆっくり浸かってきてね！' % (integer_of_diff))
            )
        elif response['Item']['vacancy'] == True and response['Item']['user_id'] != postback_user_id: # もし自分ではない他の誰かが入浴中なら
            if integer_of_diff > 2700: # 45分以上経過していたら他人の入室から自分の入室に変更する
                option = {
                    'Key': {
                        'building': 1,
                        'gender': 1
                    },
                    'UpdateExpression': 'set #vacancy = :v, #user_id = :u, #time = :t',
                    'ExpressionAttributeNames': {
                        '#vacancy': 'vacancy',
                        '#user_id': 'user_id',
                        '#time': 'time'
                    },
                    'ExpressionAttributeValues': {
                        ':v': True,
                        ':u': postback_user_id,
                        ':t': current_time
                    }
                }
                table.update_item(**option)
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='女風呂は45分以上も前から誰かが入浴中ですのでもう空いていると思うので、あなたを入浴中にしました！')
                )
            else: # 45分以上経過していないなら他人の入室から変更しない
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='女風呂は%i分前から誰かが入浴中なので今は入浴できません..！上がるまで少しお待ちを🙇‍♂' % (integer_of_diff))
                )
        elif response['Item']['vacancy'] == False: # 誰も入浴していないなら
            # DynamoDBへのPut処理実行
            option = {
                'Key': {
                    'building': 1,
                    'gender': 1
                },
                'UpdateExpression': 'set #vacancy = :v, #user_id = :u, #time = :t',
                'ExpressionAttributeNames': {
                    '#vacancy': 'vacancy',
                    '#user_id': 'user_id',
                    '#time': 'time'
                },
                'ExpressionAttributeValues': {
                    ':v': True,
                    ':u': postback_user_id,
                    ':t': current_time
                }
            }
            table.update_item(**option)
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text="あなたが女風呂に入浴中にしたよ！")
            )
    elif postback_msg == 'm_out':
        #DynamoDBへのgetItem処理実行
        response = table.get_item(Key={'building': 1, 'gender': 2})

        # DBのtimeとcurrent_timeの差分を計測し、秒数を分に変換する
        diff_between_current_and_past = (datetime.strptime(current_time,'%Y-%m-%dT%H:%M:%S') - datetime.strptime(response['Item']['time'],'%Y-%m-%dT%H:%M:%S')).seconds
        integer_of_diff = math.floor(diff_between_current_and_past / 60)

        if response['Item']['vacancy'] == True and response['Item']['user_id'] == postback_user_id: # 誰かが入っている、かつ、それが他人でないとき(自分)のみ空室にできる
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text='男風呂を「空き」にしたよ！')
            )
            option = {
                'Key': {
                    'building': 1,
                    'gender': 2
                },
                'UpdateExpression': 'set #vacancy = :v',
                'ExpressionAttributeNames': {
                    '#vacancy': 'vacancy'
                },
                'ExpressionAttributeValues': {
                    ':v': False
                }
            }
            table.update_item(**option)
        elif response['Item']['vacancy'] == True and response['Item']['user_id'] != postback_user_id: # 誰かが入っている、かつ、それが他人のときは
            if integer_of_diff > 2700: # 45分以上経過していたら他人の入室から自分の入室に変更する
                option = {
                    'Key': {
                        'building': 1,
                        'gender': 2
                    },
                    'UpdateExpression': 'set #vacancy = :v',
                    'ExpressionAttributeNames': {
                        '#vacancy': 'vacancy'
                    },
                    'ExpressionAttributeValues': {
                        ':v': False
                    }
                }
                table.update_item(**option)
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='男風呂は45分以上も前から誰かが入浴中ですので空きに変更しました！お風呂に入りたいときは青色のinを選択してね')
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='他の人が入っているときは「out」を選択できません..！今入浴中の方は%i分前に入浴し始めました！' % (integer_of_diff))
                )
        elif response['Item']['vacancy'] == False: # 誰も入っていないとき
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text='お風呂は既に「空き」だよ！')
            )
    elif postback_msg == 'm_check':
        # DynamoDBへのgetItem処理実行
        response = table.get_item(Key={'building': 1, 'gender': 2})

        # DBのtimeとcurrent_timeの差分を計測し、秒数を分に変換する
        diff_between_current_and_past = (datetime.strptime(current_time,'%Y-%m-%dT%H:%M:%S') - datetime.strptime(response['Item']['time'],'%Y-%m-%dT%H:%M:%S')).seconds
        integer_of_diff = math.floor(diff_between_current_and_past / 60)

        if response['Item']['vacancy'] == True and response['Item']['user_id'] == postback_user_id: # もし自分が入浴中になっていたら
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text='男風呂は%i分前からあなたが入浴中になっています！' % (integer_of_diff))
            )
        elif response['Item']['vacancy'] == True and response['Item']['user_id'] != postback_user_id: # もし自分以外の誰かが入浴中になっていたら
            if integer_of_diff > 2700: # 45分以上経過していたら入室から空きに変更する
                option = {
                    'Key': {
                        'building': 1,
                        'gender': 2
                    },
                    'UpdateExpression': 'set #vacancy = :v',
                    'ExpressionAttributeNames': {
                        '#vacancy': 'vacancy'
                    },
                    'ExpressionAttributeValues': {
                        ':v': False
                    }
                }
                table.update_item(**option)
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='女風呂は45分以上も前から誰かが入浴中ですので空きに変更しました！お風呂に入りたいときは青色のinを選択してね')
                )
            else: # 45分以上経過していないなら入室から変更なし
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='男風呂は%i分前から誰かが入浴中です！' % (integer_of_diff))
                )
        elif response['Item']['vacancy'] == False:
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text='男風呂は誰も入浴してません！入れます！お風呂に入りたいときは青色のinを選択してね')
            )
            
    elif postback_msg == 'm_in':
        # DynamoDBへのgetItem処理実行
        response = table.get_item(Key={'building': 1, 'gender': 2})

        # DBのtimeとcurrent_timeの差分を計測し、秒数を分に変換する
        diff_between_current_and_past = (datetime.strptime(current_time,'%Y-%m-%dT%H:%M:%S') - datetime.strptime(response['Item']['time'],'%Y-%m-%dT%H:%M:%S')).seconds
        integer_of_diff = math.floor(diff_between_current_and_past / 60)
        
        if response['Item']['vacancy'] == True and response['Item']['user_id'] == postback_user_id: # もし誰かが入浴中かつその人が自分なら
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text='もうあなたが%i分前から「入浴中」になってます！ゆっくり浸かってきてね！' % (integer_of_diff))
            )
        elif response['Item']['vacancy'] == True and response['Item']['user_id'] != postback_user_id: # もし自分ではない他の誰かが入浴中なら
            if integer_of_diff > 2700: # 45分以上経過していたら他人の入室から自分の入室に変更する
                option = {
                    'Key': {
                        'building': 1,
                        'gender': 2
                    },
                    'UpdateExpression': 'set #vacancy = :v, #user_id = :u, #time = :t',
                    'ExpressionAttributeNames': {
                        '#vacancy': 'vacancy',
                        '#user_id': 'user_id',
                        '#time': 'time'
                    },
                    'ExpressionAttributeValues': {
                        ':v': True,
                        ':u': postback_user_id,
                        ':t': current_time
                    }
                }
                table.update_item(**option)
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='女風呂は45分以上も前から誰かが入浴中ですのでもう空いていると思うので、あなたを入浴中にしました！')
                )
            else: # 45分以上経過していないなら他人の入室から変更しない
                line_bot_api.reply_message(
                    event.reply_token,
                    messages=TextSendMessage(text='男風呂は%i分前から誰かが入浴中なので今は入浴できません..！上がるまで少しお待ちを🙇‍♂' % (integer_of_diff))
                )
        elif response['Item']['vacancy'] == False: # 誰も入浴していないなら
            # DynamoDBへのPut処理実行
            option = {
                'Key': {
                    'building': 1,
                    'gender': 2
                },
                'UpdateExpression': 'set #vacancy = :v, #user_id = :u, #time = :t',
                'ExpressionAttributeNames': {
                    '#vacancy': 'vacancy',
                    '#user_id': 'user_id',
                    '#time': 'time'
                },
                'ExpressionAttributeValues': {
                    ':v': True,
                    ':u': postback_user_id,
                    ':t': current_time
                }
            }
            table.update_item(**option)
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text="あなたが男風呂に入浴中にしたよ！")
            )
