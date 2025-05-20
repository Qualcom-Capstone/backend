# dlq_worker.py (선택적으로 사용)
import pika

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

channel.queue_declare(queue='post_queue_dlq', durable=True)

def callback(ch, method, properties, body):
    print("🔴 DLQ 메시지:", body.decode())

channel.basic_consume(queue='post_queue_dlq', on_message_callback=callback, auto_ack=True)
print('🔍 DLQ 감시 중...')
channel.start_consuming()
