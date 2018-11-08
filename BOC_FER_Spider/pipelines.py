# -*- coding: utf-8 -*-
# Python内置库
import copy
import uuid
import logging

# Python第三方库

# PyMongo
import pymongo
from pymongo.errors import ConnectionFailure

# PyMySQL
import pymysql
from pymysql import cursors

# Scrapy
from scrapy.conf import settings

# Twisted
from twisted.enterprise import adbapi

# 项目内部库
from BOC_FER_Spider.utils.enum_variable import INSERT_SQL


# 日志
logger = logging.getLogger(__name__)


class BocFerSpiderMySQLPipeline(object):
    """
    保存到数据库中对应的class
    1、在settings.py文件中配置
    2、在自己实现的爬虫类中yield item,会自动执行
    """
    def __init__(self, db_pool):
        self.db_pool = db_pool

    @classmethod
    def from_settings(cls, settings):
        """
        1、@classmethod声明一个类方法，而对于平常我们见到的叫做实例方法。
        2、类方法的第一个参数cls（class的缩写，指这个类本身），而实例方法的第一个参数是self，表示该类的一个实例
        3、可以通过类来调用，就像C.f()，相当于java中的静态方法
        """
        # 读取settings中配置的数据库参数
        db_params = dict(
            host=settings['MYSQL_HOST'],
            db=settings['MYSQL_DBNAME'],
            user=settings['MYSQL_USER'],
            passwd=settings['MYSQL_PASSWD'],
            charset='utf8',  # 编码要加上，否则可能出现中文乱码问题
            cursorclass=cursors.DictCursor,
            use_unicode=False,
        )
        db_pool = adbapi.ConnectionPool('pymysql', **db_params)  # **表示将字典扩展为关键字参数,相当于host=xxx,db=yyy....
        # 相当于db_pool赋值给了这个类，self中可以得到
        return cls(db_pool)

    # pipeline默认调用
    def process_item(self, item, spider):
        # 对象拷贝，深拷贝
        async_item = copy.deepcopy(item)
        query = self.db_pool.runInteraction(self._conditional_insert, async_item)  # 调用插入的方法
        query.addErrback(self._handle_error, item, spider)  # 调用异常处理方法
        return item

    # 写入数据库中
    # SQL语句在这里
    def _conditional_insert(self, tx, item):
        params = (
                   item['currency_name'],
                   item['buying_rate'],
                   item['cash_buying_rate'],
                   item['selling_rate'],
                   item['cash_selling_rate'],
                   item['boe_conversion_rate'],
                   item['rate_time'])
        tx.execute(INSERT_SQL, params)

    # 错误处理方法
    def _handle_error(self, failue, item, spider):
        print(failue)


class BocFerSpiderMongoDBPipeline(object):
    def __init__(self):
        # MongoDB配置
        self._host = settings.get("MONGODB_HOST")
        self._port = settings.get("MONGODB_PORT")
        self._user = settings.get("MONGODB_USER")
        self._pass = settings.get("MONGODB_PASS")
        self._db_name = settings.get("MONGODB_DB_NAME")
        self._col_name = settings.get("MONGODB_COL_NAME")

        # 初始化
        self.client = None
        self.db = None
        self.collection = None
        self.conn_flag = False

    def open_spider(self, spider):
        """
        启动爬虫之后的方法
        :param spider: 爬虫对象
        :return: 无返回值
        """
        if spider.name == "BOC":
            self.client = pymongo.MongoClient(
                host=self._host,
                port=self._port,
                username=self._user,
                password=self._pass,
                socketTimeoutMS=3000
            )
            try:
                # 判断是否能够连接上MongoDB
                self.client.admin.command('ismaster')
                self.db = self.client[self._db_name]
                self.collection = self.db[self._col_name]
            except ConnectionFailure:
                logger.error("MongoDB服务未启动")

    def close_spider(self, spider):
        """
        关闭爬虫之后的方法
        :param spider: 爬虫对象
        :return: 无返回值
        """
        if spider.name == "BOC":
            self.client.close()

    def process_item(self, item, spider):
        """
        写入数据库中
        :param item: 数据条目
        :param spider: 爬虫对象
        :return: 返回显示item
        """
        try:
            item['_id'] = str(uuid.uuid4()).replace("-", "")
            self.collection.insert(item)
            return item
        except Exception as err:
            logger.error(err)
            # 结束爬虫
            spider.crawler.engine.close_spider(spider, "MongoDB insert error! Reason: {}".format(str(err)))
