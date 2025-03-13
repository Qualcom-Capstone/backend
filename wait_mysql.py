import pymysql
from time import time, sleep
import logging
def mysql_is_ready():
    check_timeout = 120
    check_interval = 5
    start_time = time()
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())
    while time() - start_time < check_timeout:
        try:
            pymysql.connect(host='mysqldb', port=3306, user='sa', password='1234', db='capstone')
            print("Connected Successfully.")
            return True
        except:
            sleep(check_interval)
    logger.error("We could not connect to {host}:{port} within {check_timeout} seconds.")
    return False
mysql_is_ready()