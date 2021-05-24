import os
import sys
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
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text)) # トークンと送信テキストをTextSendMessage(text)にて指定。ここではecho botのため、送信された内容と同じ内容を返すようにしている。
    
@handler.add(PostbackEvent)
def on_postback(event):
    # DynamoDBにデータを送信する
    dynamoDB = boto3.resource("dynamodb")
    table = dynamoDB.Table("Bath") # Bathテーブルに接続
    
    # PostBackを取得
    postback_msg = event.postback.data

    if postback_msg == 'f_out':
        line_bot_api.reply_message(
            event.reply_token,
            messages=TextSendMessage(text='今から女風呂を出るよ！')
        )
        # DynamoDBへのPut処理実行
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
    elif postback_msg == 'f_check':
        # DynamoDBへのgetItem処理実行
        response = table.get_item(Key={'building': 1, 'gender': 1})
        if response['Item']['vacancy'] == True:
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text="女風呂は誰かが入浴中です！")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text="女風呂は誰も入浴してません！入れます！")
            )
    elif postback_msg == 'f_in':
        # DynamoDBへのgetItem処理実行
        response = table.get_item(Key={'building': 1, 'gender': 1})
        if response['Item']['vacancy'] == True: # もし誰かが入浴中なら
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text="女風呂は誰かが入浴中なので今は入浴できません..！上がるまで少しお待ちを🙇‍♂")
            )
        else: # 誰も入浴していないなら
            # DynamoDBへのPut処理実行
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
                    ':v': True
                }
            }
            table.update_item(**option)
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text="入浴中にしたよ！")
            )
    elif postback_msg == 'm_out':
        line_bot_api.reply_message(
            event.reply_token,
            messages=TextSendMessage(text='今から男風呂を出るよ！')
        )
        # DynamoDBへのPut処理実行
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
    elif postback_msg == 'm_check':
        # DynamoDBへのgetItem処理実行
        response = table.get_item(Key={'building': 1, 'gender': 2})
        if response['Item']['vacancy'] == True:
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text="男風呂は誰かが入浴中です！")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text="男風呂は誰も入浴してません！入れます！")
            )
            
    elif postback_msg == 'm_in':
        # DynamoDBへのgetItem処理実行
        response = table.get_item(Key={'building': 1, 'gender': 2})
        if response['Item']['vacancy'] == True: # もし誰かが入浴中なら
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text="男風呂は誰かが入浴中なので今は入浴できません..！上がるまで少しお待ちを🙇‍♂️")
            )
        else: # 誰も入浴していないなら
            # DynamoDBへのPut処理実行
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
                    ':v': True
                }
            }
            table.update_item(**option)
            line_bot_api.reply_message(
                event.reply_token,
                messages=TextSendMessage(text="入浴中にしたよ！")
            )
