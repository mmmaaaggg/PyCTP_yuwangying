# -*- coding: utf-8 -*-
"""
Created on Wed Jul 20 08:46:13 2016

@author: YuWanying
"""


import copy
import json
from PyCTP_Trade import PyCTP_Trader_API
from PyCTP_Market import PyCTP_Market_API
from OrderAlgorithm import OrderAlgorithm
import PyCTP
import time
import Utils
from pandas import DataFrame, Series
import pandas as pd
from PyQt4 import QtCore


class Strategy(QtCore.QObject):
    # 定义信号，必须放到__init__之前
    signal_UI_spread_short = QtCore.pyqtSignal(str)  # 定义信号，设置单账户窗口空头价差值
    signal_UI_spread_long = QtCore.pyqtSignal(str)
    signal_UI_spread_short_total = QtCore.pyqtSignal(str)
    signal_UI_spread_long_total = QtCore.pyqtSignal(str)
    signal_UI_spread_short_change_color = QtCore.pyqtSignal(str)  # 定义信号，设置单账户窗口空头价差颜色
    signal_UI_spread_long_change_color = QtCore.pyqtSignal(str)
    signal_UI_spread_short_total_change_color = QtCore.pyqtSignal(str)
    signal_UI_spread_long_total_change_color = QtCore.pyqtSignal(str)

    signal_UI_change_color = QtCore.pyqtSignal(str)  # 定义信号，改变颜色

    # class Strategy功能:接收行情，接收Json数据，触发交易信号，将交易任务交给OrderAlgorithm
    def __init__(self, dict_args, obj_user, obj_DBM, parent=None):
        super(Strategy, self).__init__(parent)  # 初始化父类
        print('Strategy.__init__() 创建交易策略，user_id=', dict_args['user_id'], 'strategy_id=', dict_args['strategy_id'])
        self.__DBM = obj_DBM  # 数据库连接实例
        self.__user = obj_user  # user实例
        self.__dict_args = dict_args  # 转存形参到类的私有变量
        self.__TradingDay = self.__user.GetTradingDay()  # 获取交易日
        self.__init_finished = False  # strategy初始化状态
        self.__trade_tasking = False  # 交易任务进行中
        self.__a_order_insert_args = dict()  # a合约报单参数
        self.__b_order_insert_args = dict()  # b合约报单参数
        self.__list_position_detail = list()  # 持仓明细列表
        self.__list_order_pending = list()  # 挂单列表，报单、成交、撤单回报
        self.__instrument_a_tick = None  # A合约tick（第一腿）
        self.__instrument_b_tick = None  # B合约tick（第二腿）
        self.__spread_long = None  # 市场多头价差：A合约买一价 - B合约买一价
        self.__spread_long_volume = None  # 市场多头价差盘口挂单量min(A合约买一量 - B合约买一量)
        self.__spread_short = None  # 市场空头价差：A合约卖一价 - B合约卖一价
        self.__spread_short_volume = None  # 市场空头价差盘口挂单量：min(A合约买一量 - B合约买一量)
        self.__spread = None  # 市场最新价价差
        self.__order_ref_a = None  # A合约报单引用
        self.__order_ref_b = None  # B合约报单引用
        self.__order_ref_last = None  # 最后一次实际使用的报单引用
        self.__dictYesterdayPositoin = dict()  # 本策略昨仓
        self.__position_a_buy = 0  # 策略持仓初始值为0
        self.__position_a_buy_today = 0
        self.__position_a_buy_yesterday = 0
        self.__position_a_sell = 0
        self.__position_a_sell_today = 0
        self.__position_a_sell_yesterday = 0
        self.__position_b_buy = 0
        self.__position_b_buy_today = 0
        self.__position_b_buy_yesterday = 0
        self.__position_b_sell = 0
        self.__position_b_sell_today = 0
        self.__position_b_sell_yesterday = 0
        self.__clicked_total = False  # 策略在主窗口中被选中的标志
        self.__clicked = False  # 策略在单账户窗口中被选中的标志
        self.__dfQryTradeStrategy = DataFrame()  # 本策略的查询当天交易记录
        self.__dfQryOrderStrategy = DataFrame()  # 本策略的查询当天委托记录
        self.__last_spread_short_total = 9999999999  # 最后价差值初始值
        self.__last_spread_long_total = 9999999999
        self.__last_spread_short = 9999999999
        self.__last_spread_long = 9999999999
        self.__short_color_black_times = 0
        self.__long_color_black_times = 0
        self.__short_total_color_black_times = 0
        self.__long_total_color_black_times = 0

        self.set_arguments(dict_args)  # 设置策略参数
        # self.__user.add_instrument_id_action_counter(dict_args['list_instrument_id'])  # 将合约代码添加到user类的合约列表
        self.__a_price_tick = self.get_price_tick(self.__list_instrument_id[0])  # A合约最小跳价
        self.__b_price_tick = self.get_price_tick(self.__list_instrument_id[1])  # B合约最小跳价
        self.init_yesterday_position()  # 初始化策略昨仓
        # self.init_today_position()  # 初始化策略持仓
        # self.init_statistics()  # 初始化统计指标

    # 设置参数
    def set_arguments(self, dict_args):
        self.__dict_args = dict_args  # 将形参转存为私有变量
        # self.__DBM.update_strategy(dict_args)  # 更新数据库

        self.__trader_id = dict_args['trader_id']
        self.__user_id = dict_args['user_id']
        self.__strategy_id = dict_args['strategy_id']
        self.__list_instrument_id = dict_args['list_instrument_id']  # 合约列表
        self.__trade_model = dict_args['trade_model']  # 交易模型
        self.__order_algorithm = dict_args['order_algorithm']  # 下单算法选择标志位
        self.__buy_open = dict_args['buy_open']  # 触发买开（开多单）
        self.__sell_close = dict_args['sell_close']  # 触发卖平（平多单）
        self.__sell_open = dict_args['sell_open']  # 触发卖开（开空单）
        self.__buy_close = dict_args['buy_close']  # 触发买平（平空单）
        self.__spread_shift = dict_args['spread_shift']  # 价差让价（超价触发）
        self.__a_wait_price_tick = dict_args['a_wait_price_tick']  # A合约挂单等待最小跳数
        self.__b_wait_price_tick = dict_args['b_wait_price_tick']  # B合约挂单等待最小跳数
        self.__stop_loss = dict_args['stop_loss']  # 止损，单位为最小跳数
        self.__lots = dict_args['lots']  # 总手
        self.__lots_batch = dict_args['lots_batch']  # 每批下单手数
        self.__a_order_action_limit = dict_args['a_order_action_limit']  # A合约撤单次数限制
        self.__a_order_action_limit = dict_args['b_order_action_limit']  # B合约撤单次数限制
        self.__on_off = dict_args['StrategyOnoff']  # 策略开关，0关、1开
        self.__only_close = dict_args['only_close']  # 只平，0关、1开
        print(">>> Strategy.set_arguments() user_id=", self.__user_id, "strategy_id=", self.__strategy_id, "dict_args=", dict_args)

    # 设置持仓
    def set_position(self, dict_args):
        # self.__DBM.update_strategy(dict_args)  # 更新数据库
        self.__position_a_buy = dict_args['position_a_buy']
        self.__position_a_buy_today = dict_args['position_a_buy_today']
        self.__position_a_buy_yesterday = dict_args['position_a_buy_yesterday']
        self.__position_a_sell = dict_args['position_a_sell']
        self.__position_a_sell_today = dict_args['position_a_sell_today']
        self.__position_a_sell_yesterday = dict_args['position_a_sell_yesterday']
        self.__position_b_buy = dict_args['position_b_buy']
        self.__position_b_buy_today = dict_args['position_b_buy_today']
        self.__position_b_buy_yesterday = dict_args['position_b_buy_yesterday']
        self.__position_b_sell = dict_args['position_b_sell']
        self.__position_b_sell_today = dict_args['position_b_sell_today']
        self.__position_b_sell_yesterday = dict_args['position_b_sell_yesterday']
        print(">>> Strategy.set_arguments() user_id=", self.__user_id, "strategy_id=", self.__strategy_id, "dict_args=", dict_args)

    # 程序运行中查询策略信息，收到服务端消息之后设置策略实例参数
    def set_arguments_query_strategy_info(self, dict_args):
        print(">>> Strategy.set_arguments_query_strategy_info() user_id=", self.__user_id, "strategy_id=", self.__strategy_id)
        self.__dict_args = dict_args  # 将形参转存为私有变量
        # self.__DBM.update_strategy(dict_args)  # 更新数据库

        self.__trader_id = dict_args['trader_id']
        self.__user_id = dict_args['user_id']
        self.__strategy_id = dict_args['strategy_id']
        self.__trade_model = dict_args['trade_model']  # 交易模型
        self.__order_algorithm = dict_args['order_algorithm']  # 下单算法选择标志位
        self.__list_instrument_id = dict_args['list_instrument_id']  # 合约列表
        self.__buy_open = dict_args['buy_open']  # 触发买开（开多单）
        self.__sell_close = dict_args['sell_close']  # 触发卖平（平多单）
        self.__sell_open = dict_args['sell_open']  # 触发卖开（开空单）
        self.__buy_close = dict_args['buy_close']  # 触发买平（平空单）
        self.__spread_shift = dict_args['spread_shift']  # 价差让价（超价触发）
        self.__a_wait_price_tick = dict_args['a_wait_price_tick']  # A合约挂单等待最小跳数
        self.__b_wait_price_tick = dict_args['b_wait_price_tick']  # B合约挂单等待最小跳数
        self.__stop_loss = dict_args['stop_loss']  # 止损，单位为最小跳数
        self.__lots = dict_args['lots']  # 总手
        self.__lots_batch = dict_args['lots_batch']  # 每批下单手数
        self.__a_order_action_limit = dict_args['a_order_action_limit']  # A合约撤单次数限制
        self.__a_order_action_limit = dict_args['b_order_action_limit']  # B合约撤单次数限制
        self.__on_off = dict_args['StrategyOnoff']  # 策略开关，0关、1开
        self.__only_close = dict_args['only_close']  # 只平，0关、1开

    # 查询策略昨仓
    def QryStrategyYesterdayPosition(self):
        dict_QryStrategyYesterdayPosition = {'MsgRef': self.__user.get_CTPManager().get_ClientMain().get_SocketManager().msg_ref_add(),
                                             'MsgSendFlag': 0,  # 发送标志，客户端发出0，服务端发出1
                                             'MsgSrc': 0,  # 消息源，客户端0，服务端1
                                             'MsgType': 10,  # 查询策略昨仓
                                             'TraderID': self.__trader_id,
                                             'UserID': self.__user_id,
                                             'StrategyID': self.__strategy_id
                                             }
        json_QryStrategyYesterdayPosition = json.dumps(dict_QryStrategyYesterdayPosition)
        self.__user.get_CTPManager().get_ClientMain().get_SocketManager().send_msg(json_QryStrategyYesterdayPosition)

    # 查询策略昨仓响应
    def OnRspQryStrategyYesterdayPosition(self, dict_StrategyYesterdayPosition):
        self.__dict_StrategyYesterdayPosition = copy.deepcopy(dict_StrategyYesterdayPosition)
        # print(">>> Strategy.OnRspQryStrategyYesterdayPosition() user_id=", self.__user_id, "strategy_id=", self.__strategy_id, "self.__dict_StrategyYesterdayPosition=\n\t", self.__dict_StrategyYesterdayPosition)

    # 初始化昨仓，从服务端获得数据计算
    def init_yesterday_position(self):
        # 所有策略昨仓的list中无数据
        for i in self.__user.get_CTPManager().get_YesterdayPosition():
            if i['user_id'] == self.__user_id and i['strategy_id'] == self.__strategy_id:
                self.__dictYesterdayPositoin = copy.deepcopy(i)
                self.__position_a_buy = self.__dictYesterdayPositoin['position_a_buy']
                self.__position_a_buy_today = 0
                self.__position_a_buy_yesterday = self.__dictYesterdayPositoin['position_a_buy']
                self.__position_a_sell = self.__dictYesterdayPositoin['position_a_sell']
                self.__position_a_sell_today = 0
                self.__position_a_sell_yesterday = self.__dictYesterdayPositoin['position_a_sell']
                self.__position_b_buy = self.__dictYesterdayPositoin['position_b_buy']
                self.__position_b_buy_today = 0
                self.__position_b_buy_yesterday = self.__dictYesterdayPositoin['position_b_buy']
                self.__position_b_sell = self.__dictYesterdayPositoin['position_b_sell']
                self.__position_b_sell_today = 0
                self.__position_b_sell_yesterday = self.__dictYesterdayPositoin['position_b_sell']
        self.init_today_position()  # 昨仓初始化完成，调用初始化今仓

    # 初始化今仓，从当天成交回报数据计算
    def init_today_position(self):
        print("Strategy.init_today_position() user_id=", self.__user_id, "strategy_id=", self.__strategy_id)
        if len(self.__user.get_dfQryTrade()) > 0:  # user的交易记录为0跳过
            self.__dfQryTrade = self.__user.get_dfQryTrade()  # 获得user的交易记录
            # 从user的Trade中筛选出该策略的记录
            self.__dfQryTradeStrategy = self.__dfQryTrade[self.__dfQryTrade.StrategyID == int(self.__strategy_id)]
        if len(self.__dfQryTradeStrategy) > 0:  # strategy的交易记录为0跳过
            # 遍历本策略的trade记录，更新今仓
            for i in self.__dfQryTradeStrategy.index:
                # A成交
                if self.__dfQryTradeStrategy['InstrumentID'][i] == self.__list_instrument_id[0]:
                    if self.__dfQryTradeStrategy['OffsetFlag'][i] == '0':  # A开仓成交回报
                        if self.__dfQryTradeStrategy['Direction'][i] == '0':  # A买开仓成交回报
                            self.__position_a_buy_today += self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                        elif self.__dfQryTradeStrategy['Direction'][i] == '1':  # A卖开仓成交回报
                            self.__position_a_sell_today += self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                    elif self.__dfQryTradeStrategy['OffsetFlag'][i] == '3':  # A平今成交回报
                        if self.__dfQryTradeStrategy['Direction'][i] == '0':  # A买平今成交回报
                            self.__position_a_sell_today -= self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                        elif self.__dfQryTradeStrategy['Direction'][i] == '1':  # A卖平今成交回报
                            self.__position_a_buy_today -= self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                    elif self.__dfQryTradeStrategy['OffsetFlag'][i] == '4':  # A平昨成交回报
                        if self.__dfQryTradeStrategy['Direction'][i] == '0':  # A买平昨成交回报
                            self.__position_a_sell_yesterday -= self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                        elif self.__dfQryTradeStrategy['Direction'][i] == '1':  # A卖平昨成交回报
                            self.__position_a_buy_yesterday -= self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                    self.__position_a_buy = self.__position_a_buy_today + self.__position_a_buy_yesterday
                    self.__position_a_sell = self.__position_a_sell_today + self.__position_a_sell_yesterday
                # B成交
                elif self.__dfQryTradeStrategy['InstrumentID'][i] == self.__list_instrument_id[1]:
                    if self.__dfQryTradeStrategy['OffsetFlag'][i] == '0':  # B开仓成交回报
                        if self.__dfQryTradeStrategy['Direction'][i] == '0':  # B买开仓成交回报
                            self.__position_b_buy_today += self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                        elif self.__dfQryTradeStrategy['Direction'][i] == '1':  # B卖开仓成交回报
                            self.__position_b_sell_today += self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                    elif self.__dfQryTradeStrategy['OffsetFlag'][i] == '3':  # B平今成交回报
                        if self.__dfQryTradeStrategy['Direction'][i] == '0':  # B买平今成交回报
                            self.__position_b_sell_today -= self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                        elif self.__dfQryTradeStrategy['Direction'][i] == '1':  # B卖平今成交回报
                            self.__position_b_buy_today -= self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                    elif self.__dfQryTradeStrategy['OffsetFlag'][i] == '4':  # B平昨成交回报
                        if self.__dfQryTradeStrategy['Direction'][i] == '0':  # B买平昨成交回报
                            self.__position_b_sell_yesterday -= self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                        elif self.__dfQryTradeStrategy['Direction'][i] == '1':  # B卖平昨成交回报
                            self.__position_b_buy_yesterday -= self.__dfQryTradeStrategy['Volume'][i]  # 更新持仓
                    self.__position_b_buy = self.__position_b_buy_today + self.__position_b_buy_yesterday
                    self.__position_b_sell = self.__position_b_sell_today + self.__position_b_sell_yesterday
                if Utils.Strategy_print:
                    print("     A合约", self.__list_instrument_id[0], "今买、昨买、总买", self.__position_a_buy_today,
                          self.__position_a_buy_yesterday,
                          self.__position_a_buy, "今卖、昨卖、总卖", self.__position_a_sell_today,
                          self.__position_a_sell_yesterday,
                          self.__position_a_sell)
                    print("     B合约", self.__list_instrument_id[1], "今买、昨买、总买", self.__position_b_buy_today,
                          self.__position_b_buy_yesterday,
                          self.__position_b_buy, "今卖、昨卖、总卖", self.__position_b_sell_today,
                          self.__position_b_sell_yesterday,
                          self.__position_b_sell)
        self.__init_finished = True  # 当前策略初始化完成

    # 获取参数
    def get_arguments(self):
        return self.__dict_args
    
    # 设置strategy初始化状态
    def set_init_finished(self, bool_input):
        self.__init_finished = bool_input
    
    # 获取strategy初始化状态
    def get_init_finished(self):
        return self.__init_finished

    # 设置数据库连接实例
    def set_DBM(self, DBM):
        self.__DBM = DBM

    # 获取数据库连接实例
    def get_DBM(self):
        return self.__DBM

    # 设置user对象
    def set_user(self, user):
        self.__user = user

    # 获取user对象
    def get_user(self, user):
        return self.__user

    # 获取trader_id
    def get_trader_id(self):
        return self.__trader_id

    # 获取user_id
    def get_user_id(self):
        return self.__user_id

    # 获取strategy_id
    def get_strategy_id(self):
        return self.__strategy_id

    # 获取self.__list_instrument_id
    def get_list_instrument_id(self):
        return self.__list_instrument_id

    # 获取指定合约最小跳'PriceTick'
    def get_price_tick(self, instrument_id):
        for i in self.__user.get_CTPManager().get_instrument_info():
            if i['InstrumentID'] == instrument_id:
                return i['PriceTick']
        # for i in self.__user.get_instrument_info():
        #     if i['InstrumentID'] == instrument_id:
        #         return i['PriceTick']

    # 获取策略开关
    def get_on_off(self):
        return self.__on_off

    def get_spread_short(self):
        return self.__spread_short

    def get_spread_long(self):
        return self.__spread_long

    def set_clicked_status(self, int_input):  # 0：未选中、1：单账户窗口中被选中、2：总账户窗口中被选中
        self.__clicked_status = int_input

    def get_position(self):
        out_dict = {
            'position_a_buy': self.__position_a_buy,
            'position_a_buy_today': self.__position_a_buy_today,
            'position_a_buy_yesterday': self.__position_a_buy_yesterday,
            'position_a_sell': self.__position_a_sell,
            'position_a_sell_today': self.__position_a_sell_today,
            'position_a_sell_yesterday': self.__position_a_sell_yesterday,
            'position_b_buy': self.__position_b_buy,
            'position_b_buy_today': self.__position_b_buy_today,
            'position_b_buy_yesterday': self.__position_b_buy_yesterday,
            'position_b_sell': self.__position_b_sell,
            'position_b_sell_today': self.__position_b_sell_today,
            'position_b_sell_yesterday': self.__position_b_sell_yesterday,
        }
        return out_dict

    # 设置当前策略在单账户窗口被选中的状态，True：被选中，False：未被选中
    def set_clicked(self, in_bool):
        self.__clicked = in_bool
        # print(">>> Strategy.set_clicked() user_id=", self.__user_id, "strategy_id=", self.__strategy_id, "self.__clicked=", self.__clicked)

    def get_clicked(self):
        return self.__clicked

    # 设置当前策略在总账户窗口被选中的状态，True：被选中，False：未被选中
    def set_clicked_total(self, in_bool):
        self.__clicked_total = in_bool
        # print(">>> Strategy.set_clicked_total() user_id=", self.__user_id, "strategy_id=", self.__strategy_id, "self.__clicked_total=", self.__clicked_total)

    def get_clicked_total(self):
        return self.__clicked_total

    # QAccountWidegt设置为属性
    def set_QAccountWidget(self, obj_QAccountWidget):
        self.__QAccountWidget = obj_QAccountWidget
        self.signal_UI_spread_long.connect(self.__QAccountWidget.lineEdit_duotoujiacha.setText)  # 信号绑定，刷新单账户窗口多头价差值
        self.signal_UI_spread_short.connect(self.__QAccountWidget.lineEdit_kongtoujiacha.setText)  # 信号绑定，刷新单账户窗口空头价差值
        self.signal_UI_spread_long_change_color.connect(self.__QAccountWidget.lineEdit_duotoujiacha.setStyleSheet)  # 信号绑定，刷新单账户窗口空头价差颜色
        self.signal_UI_spread_short_change_color.connect(self.__QAccountWidget.lineEdit_kongtoujiacha.setStyleSheet)  # 信号绑定，刷新单账户窗口多头价差颜色

    def get_QAccountWidget(self):
        return self.__QAccountWidget

    # QAccountWidegtTotal设置为属性（总账户的窗口）
    def set_QAccountWidgetTotal(self, obj_QAccountWidgetTotal):
        self.__QAccountWidgetTotal = obj_QAccountWidgetTotal
        self.signal_UI_spread_long_total.connect(self.__QAccountWidgetTotal.lineEdit_duotoujiacha.setText)  # 信号槽绑定
        self.signal_UI_spread_short_total.connect(self.__QAccountWidgetTotal.lineEdit_kongtoujiacha.setText)  # 信号槽绑定
        self.signal_UI_spread_long_total_change_color.connect(self.__QAccountWidgetTotal.lineEdit_duotoujiacha.setStyleSheet)
        self.signal_UI_spread_short_total_change_color.connect(self.__QAccountWidgetTotal.lineEdit_kongtoujiacha.setStyleSheet)

    def get_QAccountWidgetTotal(self):
        return self.__QAccountWidgetTotal

    # 设置当前界面显示的窗口名称
    def set_show_widget_name(self, str_widget_name):
        self.__show_widget_name = str_widget_name
        # print(">>> Strategy.set_show_widget_name() user_id=", self.__user_id, "strategy_id=", self.__strategy_id , "show_widget_name=", self.__show_widget_name)

    def get_show_widget_name(self):
        return self.__show_widget_name

    # 生成报单引用，前两位是策略编号，后面几位递增1
    def add_order_ref(self):
        return (str(self.__user.add_order_ref_part2()) + self.__strategy_id).encode()

    # 回调函数：行情推送
    def OnRtnDepthMarketData(self, tick):
        """ 行情推送 """
        # print(">>> Strategy.OnRtnDepthMarketData() tick=", tick)
        if tick is None:
            return
        if isinstance(tick['BidPrice1'], float) is False:
            return
        if isinstance(tick['AskPrice1'], float) is False:
            return
        if isinstance(tick['BidVolume1'], int) is False:
            return
        if isinstance(tick['AskVolume1'], int) is False:
            return

        # 策略初始化未完成，跳过
        if self.__init_finished is False:
            # print("Strategy.OnRtnDepthMarketData() user_id=", self.__user_id, "strategy_id=", self.__strategy_id, "策略初始化未完成")
            return
        # CTPManager初始化未完成，跳过
        if self.__user.get_CTPManager().get_init_finished() is False:
            return
        # 窗口创建完成
        if self.__user.get_CTPManager().get_ClientMain().get_create_QAccountWidget_finished() is False:
            return

        # 过滤出B合约的tick
        if tick['InstrumentID'] == self.__list_instrument_id[1]:
            self.__instrument_b_tick = copy.deepcopy(tick)
            # print(self.__user_id + self.__strategy_id, "B合约：", self.__instrument_b_tick)
        # 过滤出A合约的tick
        elif tick['InstrumentID'] == self.__list_instrument_id[0]:
            self.__instrument_a_tick = copy.deepcopy(tick)
            # print(self.__user_id + self.__strategy_id, "A合约：", self.__instrument_a_tick)

        # 计算市场盘口价差、量
        if self.__instrument_a_tick is None or self.__instrument_b_tick is None:
            return
        self.__spread_long = self.__instrument_a_tick['BidPrice1'] - self.__instrument_b_tick['AskPrice1']
        self.__spread_long_volume = min(self.__instrument_a_tick['BidVolume1'], self.__instrument_b_tick['AskVolume1'])
        self.__spread_short = self.__instrument_a_tick['AskPrice1'] - self.__instrument_b_tick['BidPrice1']
        self.__spread_short_volume = min(self.__instrument_a_tick['AskVolume1'], self.__instrument_b_tick['BidVolume1'])

        # 没有下单任务执行中，进入选择下单算法
        if not self.__trade_tasking:
            self.select_order_algorithm(self.__order_algorithm)
        # 有下单任务执行中，跟踪交易任务
        elif self.__trade_tasking:
            dict_args = {'flag': 'tick', 'tick': tick}
            self.trade_task(dict_args)

        # 刷新界面
        self.spread_to_ui()

    def OnRspOrderInsert(self, InputOrder, RspInfo, RequestID, IsLast):
        """ 报单录入请求响应 """
        # 报单错误时响应
        if Utils.Strategy_print:
            print('Strategy.OnRspOrderInsert()', 'OrderRef:', InputOrder['OrderRef'], 'InputOrder:', InputOrder, 'RspInfo:', RspInfo, 'RequestID:', RequestID, 'IsLast:', IsLast)
        dict_args = {'flag': 'OnRspOrderInsert',
                          'InputOrder': InputOrder,
                          'RspInfo': RspInfo,
                          'RequestID': RequestID,
                          'IsLast': IsLast}
        self.trade_task(dict_args)  # 转到交易任务处理

    def OnRspOrderAction(self, InputOrderAction, RspInfo, RequestID, IsLast):
        """报单操作请求响应:撤单操作响应"""
        if Utils.Strategy_print:
            print('Strategy.OnRspOrderAction()', 'OrderRef:', InputOrderAction['OrderRef'], 'InputOrderAction:', InputOrderAction, 'RspInfo:', RspInfo, 'RequestID:', RequestID, 'IsLast:', IsLast)
        dict_args = {'flag': 'OnRspOrderAction',
                          'InputOrderAction': InputOrderAction,
                          'RspInfo': RspInfo,
                          'RequestID': RequestID,
                          'IsLast': IsLast}
        self.trade_task(dict_args)  # 转到交易任务处理

    def OnRtnOrder(self, Order):
        """报单回报"""
        from User import User
        if Utils.Strategy_print:
            print('Strategy.OnRtnOrder()', 'OrderRef:', Order['OrderRef'], 'Order', Order)

        dict_args = {'flag': 'OnRtnOrder',
                          'Order': Order}

        self.update_list_order_pending(dict_args)  # 更新挂单list
        self.update_task_status()  # 更新任务状态
        # self.update_position(dict_args)  # 更新持仓量变量（放到OnRtnTrade回调中）

        self.__user.action_counter(dict_args['Order']['InstrumentID'])  # 撤单次数添加到user类的撤单计数器
        self.trade_task(dict_args)  # 转到交易任务处理

    def OnRtnTrade(self, Trade):
        """成交回报"""
        if Utils.Strategy_print:
            print('Strategy.OnRtnTrade()', 'OrderRef:', Trade['OrderRef'], 'Trade', Trade)

        self.update_list_position_detail(Trade)  # 更新持仓明细list

        dict_args = {'flag': 'OnRtnTrade',
                          'Trade': Trade}

        self.update_position(Trade)  # 更新持仓量变量
        self.update_task_status()  # 更新任务状态
        
        self.trade_task(dict_args)  # 转到交易任务处理

    def OnErrRtnOrderAction(self, OrderAction, RspInfo):
        """ 报单操作错误回报 """
        if Utils.Strategy_print:
            print('Strategy.OnErrRtnOrderAction()', 'OrderRef:', OrderAction['OrderRef'], 'OrderAction:', OrderAction, 'RspInfo:', RspInfo)
        dict_args = {'flag': 'OnErrRtnOrderAction',
                          'OrderAction': OrderAction,
                          'RspInfo': RspInfo}
        self.trade_task(dict_args)  # 转到交易任务处理

    def OnErrRtnOrderInsert(self, InputOrder, RspInfo):
        """报单录入错误回报"""
        if Utils.Strategy_print:
            print('Strategy.OnErrRtnOrderInsert()', 'OrderRef:', InputOrder['OrderRef'], 'InputOrder:', InputOrder, 'RspInfo:', RspInfo)
        dict_args = {'flag': 'OnErrRtnOrderInsert',
                          'InputOrder': InputOrder,
                          'RspInfo': RspInfo}
        self.trade_task(dict_args)  # 转到交易任务处理

    # 选择下单算法
    def select_order_algorithm(self, flag):
        # 有挂单
        if len(self.__list_order_pending) > 0:
            return
        # 撇退
        if self.__position_a_sell != self.__position_b_buy or self.__position_a_buy != self.__position_b_sell:
            return
        # 选择执行交易算法
        if flag == '01':
            self.order_algorithm_one()
        elif flag == '02':
            self.order_algorithm_two()
        elif flag == '03':
            self.order_algorithm_three()
        else:
            # print("Strategy.select_order_algorithm() 没有选择下单算法")
            pass

    # 价差显示到界面
    def spread_to_ui(self):
        # print(">>> Strategy.market_spread() user_id=", self.__user_id, "strategy_id=", self.__strategy_id, "self.__clicked=", self.__clicked, "self.__clicked_total=", self.__clicked_total)
        # 最新值与前值相同不更新、最新值大于前值红色显示、最新值小于前值绿色显示
        # 总账户窗口中刷新价差行情
        if self.__show_widget_name == "总账户":
            if self.__clicked_total:
                # self.__QAccountWidgetTotal.update_groupBox_spread(self.__spread_short, self.__spread_long)
                # 刷新空头价差显示
                if self.__last_spread_short_total == 9999999999:  # 初始值，第一个价差显示为黑色
                    self.signal_UI_spread_short_total.emit(("%.2f" % self.__spread_short))
                    self.signal_UI_spread_short_total_change_color.emit("color: rgb(0, 0, 0);")
                else:
                    # print(">>> self.__spread_short == self.__last_spread_short_total", self.__spread_short, self.__last_spread_short_total)
                    # if self.__spread_short == self.__last_spread_short_total:
                    #     self.__short_color_black_times += 1
                    #     if self.__short_color_black_times == 8:
                    #         self.signal_UI_spread_short_total.emit(("%.2f" % self.__spread_short))
                    #         self.signal_UI_spread_short_total_change_color.emit("color: black;")
                    #         self.__short_color_black_times = 0
                    # el
                    if self.__spread_short > self.__last_spread_short_total:
                        self.signal_UI_spread_short_total.emit(("%.2f" % self.__spread_short))
                        self.signal_UI_spread_short_total_change_color.emit("color: rgb(255, 0, 0);font-weight:bold;")
                    elif self.__spread_short < self.__last_spread_short_total:
                        self.signal_UI_spread_short_total.emit(("%.2f" % self.__spread_short))
                        self.signal_UI_spread_short_total_change_color.emit("color: rgb(0, 170, 0);font-weight:bold;")
                # 刷新多头价差显示
                if self.__last_spread_long_total == 9999999999:  # 初始值，第一个价差显示为黑色
                    self.signal_UI_spread_long_total.emit(("%.2f" % self.__spread_long))
                    self.signal_UI_change_color.emit("color: rgb(0, 0, 0);")
                else:
                    # if self.__spread_long == self.__last_spread_long_total:
                    #     # self.signal_UI_spread_long_total.emit(("%.2f" % self.__spread_long))
                    #     self.signal_UI_spread_long_total_change_color.emit("color: black;")
                    # el
                    if self.__spread_long > self.__last_spread_long_total:
                        self.signal_UI_spread_long_total.emit(("%.2f" % self.__spread_long))
                        self.signal_UI_spread_long_total_change_color.emit("color: rgb(255, 0, 0);font-weight:bold;")
                    elif self.__spread_long < self.__last_spread_long_total:
                        self.signal_UI_spread_long_total.emit(("%.2f" % self.__spread_long))
                        self.signal_UI_spread_long_total_change_color.emit("color: rgb(0, 170, 0);font-weight:bold;")
                # 更新最后一次价差值
                self.__last_spread_short_total = self.__spread_short  # 总账户窗口中最后的空头价差
                self.__last_spread_long_total = self.__spread_long  # 总账户窗口中最后的空头价差

        # 单账户窗口中刷新价差行情
        elif self.__show_widget_name == self.__user_id:
            if self.__clicked:
                # self.__QAccountWidgetTotal.update_groupBox_spread(self.__spread_short, self.__spread_long)
                # 刷新空头价差显示
                if self.__last_spread_short == 9999999999:  # 初始值，第一个价差显示为黑色
                    self.signal_UI_spread_short.emit(("%.2f" % self.__spread_short))
                    self.signal_UI_spread_short_change_color.emit("color: rgb(0, 0, 0);")
                else:
                    # print(">>> self.__spread_short == self.__last_spread_short", self.__spread_short, self.__last_spread_short)
                    # if self.__spread_short == self.__last_spread_short:
                    #     self.signal_UI_spread_short.emit(("%.2f" % self.__spread_short))
                    #     self.signal_UI_spread_short_change_color.emit("color: black;")
                    # el
                    if self.__spread_short > self.__last_spread_short:
                        self.signal_UI_spread_short.emit(("%.2f" % self.__spread_short))
                        self.signal_UI_spread_short_change_color.emit("color: rgb(255, 0, 0);font-weight:bold;")
                    elif self.__spread_short < self.__last_spread_short:
                        self.signal_UI_spread_short.emit(("%.2f" % self.__spread_short))
                        self.signal_UI_spread_short_change_color.emit("color: rgb(0, 170, 0);font-weight:bold;")
                # 刷新多头价差显示
                if self.__last_spread_long == 9999999999:  # 初始值，第一个价差显示为黑色
                    self.signal_UI_spread_long.emit(("%.2f" % self.__spread_long))
                    self.signal_UI_change_color.emit("color: rgb(0, 0, 0);")
                else:
                    # if self.__spread_long == self.__last_spread_long:
                    #     # self.signal_UI_spread_long.emit(("%.2f" % self.__spread_long))
                    #     self.signal_UI_spread_long_change_color.emit("color: black;")
                    # el
                    if self.__spread_long > self.__last_spread_long:
                        self.signal_UI_spread_long.emit(("%.2f" % self.__spread_long))
                        self.signal_UI_spread_long_change_color.emit("color: rgb(255, 0, 0);font-weight:bold;")
                    elif self.__spread_long < self.__last_spread_long:
                        self.signal_UI_spread_long.emit(("%.2f" % self.__spread_long))
                        self.signal_UI_spread_long_change_color.emit("color: rgb(0, 170, 0);font-weight:bold;")
                # 更新最后一次价差值
                self.__last_spread_short = self.__spread_short  # 总账户窗口中最后的空头价差
                self.__last_spread_long = self.__spread_long  # 总账户窗口中最后的空头价差

    # 下单算法1：A合约以对手价发单，B合约以对手价发单
    def order_algorithm_one(self):

        # 有任何一个合约是无效行情则跳过
        if self.__instrument_a_tick is not None or self.__instrument_b_tick is not None:
            return

        # 策略开关为关则直接跳出，不执行开平仓逻辑判断，依次为：策略开关、单个期货账户开关（user）、总开关（trader）
        if self.__on_off == 0 or self.__user.get_on_off() == 0 or self.__user.get_CTPManager().get_on_off() == 0:
            print("Strategy.order_algorithm_one() 策略开关状态", self.__on_off, self.__user.get_on_off(), self.__user.get_CTPManager().get_on_off())
            return

        # 价差卖平
        if self.__spread_long >= self.__sell_close \
                and self.__position_a_sell == self.__position_b_buy \
                and self.__position_a_sell > 0:
            '''
                市场多头价差大于等于策略卖平触发参数
                A、B合约持仓量相等且大于0
            '''
            if Utils.Strategy_print:
                print("Strategy.order_algorithm_one() 策略编号", self.__strategy_id, "交易信号触发", "价差买平")
            # 打印价差
            if Utils.Strategy_print:
                print("Strategy.order_algorithm_one() 策略编号", self.__user_id + self.__strategy_id,
                      self.__list_instrument_id, self.__spread_long, "(", self.__spread_long_volume, ")",
                      self.__spread_short, "(", self.__spread_short_volume, ")")
            # 满足交易任务之前的一个tick
            self.__instrument_a_tick_after_tasking = self.__instrument_a_tick
            self.__instrument_b_tick_after_tasking = self.__instrument_b_tick
            # 优先平昨仓
            # 报单手数：盘口挂单量、每份发单手数、持仓量
            if self.__position_a_sell_yesterday > 0:
                order_volume = min(self.__spread_short_volume,
                                   self.__lots_batch,
                                   self.__position_a_sell_yesterday)
                CombOffsetFlag = b'4'  # 平昨标志
            elif self.__position_a_sell_yesterday == 0 and self.__position_a_sell_today > 0:
                order_volume = min(self.__spread_short_volume,
                                   self.__lots_batch,
                                   self.__position_a_sell_today)
                CombOffsetFlag = b'3'  # 平今标志
            if order_volume <= 0 or not isinstance(order_volume, int):
                if Utils.Strategy_print:
                    print('Strategy.order_algorithm_one() 发单手数错误值', order_volume)
            self.__order_ref_a = self.add_order_ref()  # 报单引用
            self.__order_ref_last = self.__order_ref_a
            # A合约报单参数，全部确定
            self.__a_order_insert_args = {'flag': 'OrderInsert',  # 标志位：报单
                                          'OrderRef': self.__order_ref_a,  # 报单引用
                                          'InstrumentID': self.__list_instrument_id[0].encode(),  # 合约代码
                                          'LimitPrice': self.__instrument_a_tick['BidPrice1'],  # 限价
                                          'VolumeTotalOriginal': order_volume,  # 数量
                                          'Direction': b'0',  # 买卖，0买,1卖
                                          'CombOffsetFlag': CombOffsetFlag,  # 组合开平标志，0开仓，上期所3平今、4平昨，其他交易所1平仓
                                          'CombHedgeFlag': b'1',  # 组合投机套保标志:1投机、2套利、3保值
                                          }
            # B合约报单参数，部分确定，报单引用和报单数量，根据A合约成交情况确定
            self.__b_order_insert_args = {'flag': 'OrderInsert',  # 标志位：报单
                                          # 'OrderRef': self.__order_ref_b,  # 报单引用
                                          'InstrumentID': self.__list_instrument_id[1].encode(),  # 合约代码
                                          'LimitPrice': self.__instrument_b_tick['AskPrice1'],  # 限价
                                          # 'VolumeTotalOriginal': order_volume,  # 数量
                                          'Direction': b'1',  # 买卖，0买,1卖
                                          'CombOffsetFlag': CombOffsetFlag,  # 组合开平标志，0开仓，上期所3平今、4平昨，其他交易所1平仓
                                          'CombHedgeFlag': b'1',  # 组合投机套保标志:1投机、2套利、3保值
                                          }
            self.trade_task(self.__a_order_insert_args)  # 执行下单任务
            self.__trade_tasking = True  # 交易任务执行中
        # 价差买平
        elif self.__spread_short <= self.__buy_close\
                and self.__position_a_sell == self.__position_b_buy\
                and self.__position_a_sell > 0:
            '''
                市场空头价差小于等于策略买平触发参数
                A、B合约持仓量相等且大于0
            '''
            if Utils.Strategy_print:
                print("Strategy.order_algorithm_one() 策略编号", self.__strategy_id, "交易信号触发", "价差买平")
            # 打印价差
            if Utils.Strategy_print:
                print("Strategy.order_algorithm_one() 策略编号", self.__user_id + self.__strategy_id, self.__list_instrument_id, self.__spread_long, "(", self.__spread_long_volume, ")", self.__spread_short, "(", self.__spread_short_volume, ")")
            # 满足交易任务之前的一个tick
            self.__instrument_a_tick_after_tasking = self.__instrument_a_tick
            self.__instrument_b_tick_after_tasking = self.__instrument_b_tick
            # 优先平昨仓
            # 报单手数：盘口挂单量、每份发单手数、持仓量
            if self.__position_a_sell_yesterday > 0:
                order_volume = min(self.__spread_short_volume,
                                   self.__lots_batch,
                                   self.__position_a_sell_yesterday)
                CombOffsetFlag = b'4'  # 平昨标志
            elif self.__position_a_sell_yesterday == 0 and self.__position_a_sell_today > 0:
                order_volume = min(self.__spread_short_volume,
                                   self.__lots_batch,
                                   self.__position_a_sell_today)
                CombOffsetFlag = b'3'  # 平今标志
            if order_volume <= 0 or not isinstance(order_volume, int):
                if Utils.Strategy_print:
                    print('Strategy.order_algorithm_one() 发单手数错误值', order_volume)
            self.__order_ref_a = self.add_order_ref()  # 报单引用
            self.__order_ref_last = self.__order_ref_a
            # A合约报单参数，全部确定
            self.__a_order_insert_args = {'flag': 'OrderInsert',  # 标志位：报单
                                          'OrderRef': self.__order_ref_a,  # 报单引用
                                          'InstrumentID': self.__list_instrument_id[0].encode(),  # 合约代码
                                          'LimitPrice': self.__instrument_a_tick['AskPrice1'],  # 限价
                                          'VolumeTotalOriginal': order_volume,  # 数量
                                          'Direction': b'0',  # 买卖，0买,1卖
                                          'CombOffsetFlag': CombOffsetFlag,  # 组合开平标志，0开仓，上期所3平今、4平昨，其他交易所1平仓
                                          'CombHedgeFlag': b'1',  # 组合投机套保标志:1投机、2套利、3保值
                                          }
            # B合约报单参数，部分确定，报单引用和报单数量，根据A合约成交情况确定
            self.__b_order_insert_args = {'flag': 'OrderInsert',  # 标志位：报单
                                          # 'OrderRef': self.__order_ref_b,  # 报单引用
                                          'InstrumentID': self.__list_instrument_id[1].encode(),  # 合约代码
                                          'LimitPrice': self.__instrument_b_tick['BidPrice1'],  # 限价
                                          # 'VolumeTotalOriginal': order_volume,  # 数量
                                          'Direction': b'1',  # 买卖，0买,1卖
                                          'CombOffsetFlag': CombOffsetFlag,  # 组合开平标志，0开仓，上期所3平今、4平昨，其他交易所1平仓
                                          'CombHedgeFlag': b'1',  # 组合投机套保标志:1投机、2套利、3保值
                                          }
            self.trade_task(self.__a_order_insert_args)  # 执行下单任务
            self.__trade_tasking = True  # 交易任务执行中
        # 价差卖开
        elif self.__spread_long >= self.__sell_open \
                and self.__position_a_buy + self.__position_a_sell < self.__lots:
            '''
            市场多头价差大于策略卖开触发参数
            策略多头持仓量+策略空头持仓量小于策略参数总手
            '''
            if Utils.Strategy_print:
                print("Strategy.order_algorithm_one() 策略编号", self.__strategy_id, "交易信号触发", "价差卖开")
            # 打印价差
            if Utils.Strategy_print:
                print(self.__user_id + self.__strategy_id, self.__list_instrument_id, self.__spread_long, "(",
                      self.__spread_long_volume, ")", self.__spread_short, "(", self.__spread_short_volume, ")")
            # 满足交易任务之前的一个tick
            self.__instrument_a_tick_after_tasking = self.__instrument_a_tick
            self.__instrument_b_tick_after_tasking = self.__instrument_b_tick
            # 报单手数：盘口挂单量、每份发单手数、剩余可开仓手数中取最小值
            order_volume = min(self.__spread_long_volume,  # 市场对手量
                               self.__lots_batch,  # 每份量
                               self.__lots - (self.__position_a_buy + self.__position_b_buy))  # 剩余可开数量
            if order_volume <= 0 or not isinstance(order_volume, int):
                if Utils.Strategy_print:
                    print('Strategy.order_algorithm_one() 发单手数错误值', order_volume)
            self.__order_ref_a = self.add_order_ref()  # 报单引用
            self.__order_ref_last = self.__order_ref_a
            # A合约报单参数，全部确定
            self.__a_order_insert_args = {'flag': 'OrderInsert',  # 标志位：报单
                                          'OrderRef': self.__order_ref_a,  # 报单引用
                                          'InstrumentID': self.__list_instrument_id[0].encode(),  # 合约代码
                                          'LimitPrice': self.__instrument_a_tick['BidPrice1'],  # 限价
                                          'VolumeTotalOriginal': order_volume,  # 数量
                                          'Direction': b'1',  # 买卖，0买,1卖
                                          'CombOffsetFlag': b'0',  # 组合开平标志，0开仓，上期所3平今、4平昨，其他交易所1平仓
                                          'CombHedgeFlag': b'1',  # 组合投机套保标志:1投机、2套利、3保值
                                          }
            # B合约报单参数，部分确定，报单引用和报单数量，根据A合约成交情况确定
            self.__b_order_insert_args = {'flag': 'OrderInsert',  # 标志位：报单
                                          # 'OrderRef': self.__order_ref_b,  # 报单引用
                                          'InstrumentID': self.__list_instrument_id[1].encode(),  # 合约代码
                                          'LimitPrice': self.__instrument_b_tick['AskPrice1'],  # 限价
                                          # 'VolumeTotalOriginal': order_volume,  # 数量
                                          'Direction': b'0',  # 买卖，0买,1卖
                                          'CombOffsetFlag': b'0',  # 组合开平标志，0开仓，上期所3平今、4平昨，其他交易所1平仓
                                          'CombHedgeFlag': b'1',  # 组合投机套保标志:1投机、2套利、3保值
                                          }
            self.trade_task(self.__a_order_insert_args)  # 执行下单任务
            self.__trade_tasking = True  # 交易任务执行中

        # 价差买开
        elif self.__spread_short <= self.__buy_open \
                and self.__position_a_buy + self.__position_a_sell < self.__lots:
            '''
            市场空头价差小于策略买开触发参数
            策略多头持仓量+策略空头持仓量小于策略参数总手
            '''
            if Utils.Strategy_print:
                print("Strategy.order_algorithm_one() 策略编号", self.__strategy_id, "交易信号触发", "价差卖开")
            # 打印价差
            if Utils.Strategy_print:
                print(self.__user_id + self.__strategy_id, self.__list_instrument_id, self.__spread_long, "(",
                      self.__spread_long_volume, ")", self.__spread_short, "(", self.__spread_short_volume, ")")
            # 满足交易任务之前的一个tick
            self.__instrument_a_tick_after_tasking = self.__instrument_a_tick
            self.__instrument_b_tick_after_tasking = self.__instrument_b_tick
            # 报单手数：盘口挂单量、每份发单手数、剩余可开仓手数中取最小值
            order_volume = min(self.__spread_long_volume,  # 市场对手量
                               self.__lots_batch,  # 每份量
                               self.__lots - (self.__position_a_buy + self.__position_b_buy))  # 剩余可开数量
            if order_volume <= 0 or not isinstance(order_volume, int):
                if Utils.Strategy_print:
                    print('Strategy.order_algorithm_one() 发单手数错误值', order_volume)
            self.__order_ref_a = self.add_order_ref()  # 报单引用
            self.__order_ref_last = self.__order_ref_a
            # A合约报单参数，全部确定
            self.__a_order_insert_args = {'flag': 'OrderInsert',  # 标志位：报单
                                          'OrderRef': self.__order_ref_a,  # 报单引用
                                          'InstrumentID': self.__list_instrument_id[0].encode(),  # 合约代码
                                          'LimitPrice': self.__instrument_a_tick['AskPrice1'],  # 限价
                                          'VolumeTotalOriginal': order_volume,  # 数量
                                          'Direction': b'0',  # 买卖，0买,1卖
                                          'CombOffsetFlag': b'0',  # 组合开平标志，0开仓，上期所3平今、4平昨，其他交易所1平仓
                                          'CombHedgeFlag': b'1',  # 组合投机套保标志:1投机、2套利、3保值
                                          }
            # B合约报单参数，部分确定，报单引用和报单数量，根据A合约成交情况确定
            self.__b_order_insert_args = {'flag': 'OrderInsert',  # 标志位：报单
                                          # 'OrderRef': self.__order_ref_b,  # 报单引用
                                          'InstrumentID': self.__list_instrument_id[1].encode(),  # 合约代码
                                          'LimitPrice': self.__instrument_b_tick['BidPrice1'],  # 限价
                                          # 'VolumeTotalOriginal': order_volume,  # 数量
                                          'Direction': b'1',  # 买卖，0买,1卖
                                          'CombOffsetFlag': b'0',  # 组合开平标志，0开仓，上期所3平今、4平昨，其他交易所1平仓
                                          'CombHedgeFlag': b'1',  # 组合投机套保标志:1投机、2套利、3保值
                                          }
            self.trade_task(self.__a_order_insert_args)  # 执行下单任务
            self.__trade_tasking = True  # 交易任务执行中

    # 下单算法2：A合约以最新成交价发单，B合约以对手价发单
    def order_algorithm_two(self):
        if Utils.Strategy_print:
            # print("Strategy.order_algorithm_two()")
            pass

    # 下单算法3：A合约以挂单价发单，B合约以对手价发单
    def order_algorithm_three(self):
        if Utils.Strategy_print:
            # print("Strategy.order_algorithm_three()")
            pass

    def trade_task(self, dict_args):
        """"交易任务执行"""
        # 报单
        if dict_args['flag'] == 'OrderInsert':
            """交易任务开始入口"""
            if Utils.Strategy_print:
                print('Strategy.trade_task() A合约报单，OrderRef=', dict_args['OrderRef'], '报单参数：', dict_args)
            self.__user.get_trade().OrderInsert(dict_args)  # A合约报单
        # 报单录入请求响应
        elif dict_args['flag'] == 'OnRspOrderInsert':
            if Utils.Strategy_print:
                print("Strategy.trade_task() 报单录入请求响应")
            pass
        # 报单操作请求响应
        elif dict_args['flag'] == 'OnRspOrderAction':
            if Utils.Strategy_print:
                print("Strategy.trade_task() 报单操作请求响应")
            pass
        # 报单回报
        elif dict_args['flag'] == 'OnRtnOrder':
            # A成交回报，B发送等量的报单(OrderInsert)
            if dict_args['Order']['InstrumentID'] == self.__list_instrument_id[0] \
                    and dict_args['Order']['OrderStatus'] in ['0', '1']:  # OrderStatus全部成交或部分成交
                # 无挂单，当前报单回报中的VolumeTrade就是本次成交量
                if len(self.__list_order_pending) == 0:
                    self.__b_order_insert_args['VolumeTotalOriginal'] = dict_args['Order']['VolumeTraded']
                # 有挂单，从挂单列表中查找是否有相同的OrderRef
                else:
                    b_fined = False  # 是否找到的初始值
                    for i in self.__list_order_pending:
                        # 从挂单列表中找到相同的OrderRef记录，当前回报的VolumeTraded减去上一条回报中VolumeTrade等于本次成交量
                        if i['OrderRef'] == dict_args['Order']['OrderRef']:
                            self.__b_order_insert_args['VolumeTotalOriginal'] = \
                                dict_args['Order']['VolumeTraded'] - i['VolumeTraded']  # B发单量等于本次回报A的成交量
                            b_fined = True  # 找到了，赋值为真
                            break
                    # 未在挂单列表中找到相同的OrderRef记录，当前报单回报中的VolumeTraded就是本次成交量
                    if not b_fined:
                        self.__b_order_insert_args['VolumeTotalOriginal'] = dict_args['Order']['VolumeTraded']

                self.__order_ref_b = self.add_order_ref()  # B报单引用
                self.__order_ref_last = self.__order_ref_b  # 实际最后使用的报单引用
                self.__b_order_insert_args['OrderRef'] = self.__order_ref_b
                if Utils.Strategy_print:
                    print('Strategy.trade_task() B合约报单，OrderRef=', self.__b_order_insert_args['OrderRef'], '报单参数：', self.__b_order_insert_args)
                self.__user.get_trade().OrderInsert(self.__b_order_insert_args)  # B合约报单
            # B成交回报
            elif dict_args['Order']['InstrumentID'] == self.__list_instrument_id[1] \
                    and dict_args['Order']['OrderStatus'] in ['0', '1']:  # OrderStatus全部成交或部分成交
                pass
            # B撤单回报，启动B重新发单一定成交策略
            elif dict_args['Order']['InstrumentID'] == self.__list_instrument_id[1] \
                    and dict_args['Order']['OrderStatus'] == '5' \
                    and len(dict_args['Order']['OrderSysID']) == 12:
                if Utils.Strategy_print:
                    print("Strategy.trade_task() 策略编号：", self.__user_id+self.__strategy_id, "收到B撤单回报，启动B重新发单一定成交策略")
                self.__order_ref_b = self.add_order_ref()  # B报单引用
                self.__order_ref_last = self.__order_ref_b  # 实际最后使用的报单引用
                if dict_args['Order']['Direction'] == '0':
                    LimitPrice = self.__instrument_b_tick['AskPrice1']  # B报单价格，找市场最新对手价
                elif dict_args['Order']['Direction'] == '1':
                    LimitPrice = self.__instrument_b_tick['BidPrice1']
                self.__b_order_insert_args = {'flag': 'OrderInsert',  # 标志位：报单
                                              'OrderRef': self.__order_ref_b,  # 报单引用
                                              'InstrumentID': self.__list_instrument_id[1].encode(),  # 合约代码
                                              'LimitPrice': LimitPrice,  # 限价
                                              'VolumeTotalOriginal': dict_args['Order']['VolumeTotal'],  # 撤单回报中的剩余未成交数量
                                              'Direction': dict_args['Order']['Direction'].encode(),  # 买卖，0买,1卖
                                              'CombOffsetFlag': dict_args['Order']['CombOffsetFlag'].encode(),  # 组合开平标志，0开仓，上期所3平今、4平昨，其他交易所1平仓
                                              'CombHedgeFlag': dict_args['Order']['CombHedgeFlag'].encode(),  # 组合投机套保标志:1投机、2套利、3保值
                                              }

                if Utils.Strategy_print:
                    print('Strategy.trade_task() B合约报单，OrderRef=', self.__b_order_insert_args['OrderRef'], '报单参数：', self.__b_order_insert_args)
                self.__user.get_trade().OrderInsert(self.__b_order_insert_args)  # B合约报单
        # 报单录入错误回报
        elif dict_args['flag'] == 'OnErrRtnOrderInsert':
            if Utils.Strategy_print:
                print("Strategy.trade_task() 报单录入错误回报")
            pass
        # 报单操作错误回报
        elif dict_args['flag'] == 'OnErrRtnOrderAction':
            if Utils.Strategy_print:
                print("Strategy.trade_task() 报单操作错误回报")
            pass
        # 行情回调，并且交易任务进行中
        elif dict_args['flag'] == 'tick' and self.__trade_tasking:
            """当交易任务进行中时，判断是否需要撤单"""
            # print("Strategy.trade_task() tick驱动判断是否需要撤单")
            # 遍历挂单列表
            for i in self.__list_order_pending:
                # A有挂单，判断是否需要撤单
                if i['InstrumentID'] == self.__list_instrument_id[0]:
                    # 通过A最新tick判断A合约是否需要撤单
                    if dict_args['tick']['InstrumentID'] == self.__list_instrument_id[0]:
                        # A挂单的买卖方向为买
                        if i['Direction'] == '0':
                            # 挂单价格与盘口买一价比较，如果与盘口价格差距n个最小跳以上，撤单
                            # print("Strategy.trade_task()self.__a_wait_price_tick * self.__a_price_tick", self.__a_wait_price_tick, self.__a_price_tick,type(self.__a_wait_price_tick), type(self.__a_price_tick))
                            if dict_args['tick']['BidPrice1'] > (i['LimitPrice'] + self.__a_wait_price_tick*self.__a_price_tick):
                                if Utils.Strategy_print:
                                    print("Strategy.trade_task() 通过A最新tick判断A合约买挂单符合撤单条件")
                                # A合约撤单
                                order_action_arguments = {'OrderRef': i['OrderRef'].encode(),
                                                          'ExchangeID': i['ExchangeID'].encode(),
                                                          'OrderSysID': i['OrderSysID'].encode()}
                                if Utils.Strategy_print:
                                    print('Strategy.trade_task() A合约撤单，OrderRef=', i['OrderRef'], '撤单参数：', order_action_arguments)
                                self.__user.get_trade().OrderAction(order_action_arguments)
                        # A挂单的买卖方向为卖
                        elif i['Direction'] == '1':
                            # 挂单价格与盘口卖一价比较，如果与盘口价格差距n个最小跳以上，撤单
                            # print("Strategy.trade_task()self.__a_wait_price_tick * self.__a_price_tick", self.__a_wait_price_tick, self.__a_price_tick,type(self.__a_wait_price_tick), type(self.__a_price_tick))
                            if dict_args['tick']['AskPrice1'] <= (i['LimitPrice'] - self.__a_wait_price_tick * self.__a_price_tick):
                                if Utils.Strategy_print:
                                    print("Strategy.trade_task() 通过A最新tick判断A合约卖挂单符合撤单条件")
                                # A合约撤单
                                order_action_arguments = {'OrderRef': i['OrderRef'].encode(),
                                                          'ExchangeID': i['ExchangeID'].encode(),
                                                          'OrderSysID': i['OrderSysID'].encode()}
                                if Utils.Strategy_print:
                                    print('Strategy.trade_task()A合约撤单，OrderRef=', i['OrderRef'], '撤单参数：', order_action_arguments)
                                self.__user.get_trade().OrderAction(order_action_arguments)
                    # 通过B最新tick判断A合约是否需要撤单
                    elif dict_args['tick']['InstrumentID'] == self.__list_instrument_id[1]:
                        # A挂单的买卖方向为买
                        if i['Direction'] == '0':
                            # B最新tick的对手价如果与开仓信号触发时B的tick对手价发生不利变化则A撤单
                            if dict_args['tick']['BidPrice1'] < self.__instrument_b_tick_after_tasking['BidPrice1']:
                                if Utils.Strategy_print:
                                    print("Strategy.trade_task() 通过B最新tick判断A合约买挂单符合撤单条件")
                                # A合约撤单
                                order_action_arguments = {'OrderRef': i['OrderRef'].encode(),
                                                          'ExchangeID': i['ExchangeID'].encode(),
                                                          'OrderSysID': i['OrderSysID'].encode()}
                                if Utils.Strategy_print:
                                    print('Strategy.trade_task() A合约撤单，OrderRef=', i['OrderRef'], '撤单参数：', order_action_arguments)
                                self.__user.get_trade().OrderAction(order_action_arguments)
                        # A挂单的买卖方向为卖
                        elif i['Direction'] == '1':
                            # B最新tick的对手价如果与开仓信号触发时B的tick对手价发生不利变化则A撤单
                            if dict_args['tick']['AskPrice1'] > self.__instrument_b_tick_after_tasking['AskPrice1']:
                                if Utils.Strategy_print:
                                    print("Strategy.trade_task()通过B最新tick判断A合约卖挂单符合撤单条件")
                                # A合约撤单
                                order_action_arguments = {'OrderRef': i['OrderRef'].encode(),
                                                          'ExchangeID': i['ExchangeID'].encode(),
                                                          'OrderSysID': i['OrderSysID'].encode()}
                                if Utils.Strategy_print:
                                    print('Strategy.trade_task() A合约撤单，OrderRef=', i['OrderRef'], '撤单参数：', order_action_arguments)
                                self.__user.get_trade().OrderAction(order_action_arguments)
                # B有挂单，判断是否需要撤单，并启动B合约一定成交策略
                if i['InstrumentID'] == self.__list_instrument_id[1]:
                    # 通过B最新tick判断B合约是否需要撤单
                    if dict_args['tick']['InstrumentID'] == self.__list_instrument_id[1]:
                        # B挂单的买卖方向为买
                        if i['Direction'] == '0':
                            # 挂单价格与盘口买一价比较，如果与盘口价格差距n个最小跳以上，撤单
                            if Utils.Strategy_print:
                                print("Strategy.trade_task() self.__b_wait_price_tick * self.__b_price_tick", self.__b_wait_price_tick, self.__b_price_tick, type(self.__b_wait_price_tick), type(self.__b_price_tick))
                            if dict_args['tick']['BidPrice1'] >= (i['LimitPrice'] + self.__b_wait_price_tick * self.__b_price_tick):
                                if Utils.Strategy_print:
                                    print("Strategy.trade_task() 通过B最新tick判断B合约买挂单符合撤单条件")
                                # B合约撤单
                                order_action_arguments = {'OrderRef': i['OrderRef'].encode(),
                                                          'ExchangeID': i['ExchangeID'].encode(),
                                                          'OrderSysID': i['OrderSysID'].encode()}
                                if Utils.Strategy_print:
                                    print('Strategy.trade_task() B合约撤单，OrderRef=', i['OrderRef'], '撤单参数：', order_action_arguments)
                                self.__user.get_trade().OrderAction(order_action_arguments)
                        # B挂单的买卖方向为卖
                        elif i['Direction'] == '1':
                            # 挂单价格与盘口卖一价比较，如果与盘口价格差距n个最小跳以上，撤单
                            if Utils.Strategy_print:
                                print("Strategy.trade_task() self.__b_wait_price_tick * self.__b_price_tick", self.__b_wait_price_tick, self.__b_price_tick, type(self.__b_wait_price_tick), type(self.__b_price_tick))
                            if dict_args['tick']['AskPrice1'] <= (i['LimitPrice'] - self.__b_wait_price_tick * self.__b_price_tick):
                                if Utils.Strategy_print:
                                    print("Strategy.trade_task() 通过B最新tick判断B合约卖挂单符合撤单条件")
                                # B合约撤单
                                order_action_arguments = {'OrderRef': i['OrderRef'].encode(),
                                                          'ExchangeID': i['ExchangeID'].encode(),
                                                          'OrderSysID': i['OrderSysID'].encode()}
                                if Utils.Strategy_print:
                                    print('Strategy.trade_task() B合约撤单，OrderRef=', i['OrderRef'], '撤单参数：', order_action_arguments)
                                self.__user.get_trade().OrderAction(order_action_arguments)
            # 若无挂单、无撇退，则交易任务已完成
            # if True:
            #     self.__trade_tasking = False

    '''
    typedef char TThostFtdcOrderStatusType
    THOST_FTDC_OST_AllTraded = b'0'  # 全部成交
    THOST_FTDC_OST_PartTradedQueueing = b'1'  # 部分成交还在队列中
    THOST_FTDC_OST_PartTradedNotQueueing = b'2'  # 部分成交不在队列中
    THOST_FTDC_OST_NoTradeQueueing = b'3'  # 未成交还在队列中
    THOST_FTDC_OST_NoTradeNotQueueing = b'4'  # 未成交不在队列中
    THOST_FTDC_OST_Canceled = b'5'  # 撤单
    THOST_FTDC_OST_Unknown = b'a'  # 未知
    THOST_FTDC_OST_NotTouched = b'b'  # 尚未触发
    THOST_FTDC_OST_Touched = b'c'  # 已触发
    '''
    # 更新挂单列表
    def update_list_order_pending(self, dict_args):
        if Utils.Strategy_print:
            print("Strategy.update_list_order_pending() 更新前self.__list_order_pending=", self.__list_order_pending)
        # 交易所返回的报单回报，处理以上九种状态
        if len(dict_args['Order']['OrderSysID']) == 12:
            # 挂单列表为空时直接添加挂单到list中
            if len(self.__list_order_pending) == 0:
                self.__list_order_pending.append(dict_args['Order'])
                return
            # 挂单列表不为空时
            for i in range(len(self.__list_order_pending)):  # 遍历挂单列表
                # 找到回报与挂单列表中OrderRef相同的记录
                if self.__list_order_pending[i]['OrderRef'] == dict_args['Order']['OrderRef']:
                    if dict_args['Order']['OrderStatus'] == '0':  # 全部成交
                        self.__list_order_pending.remove(self.__list_order_pending[i])  # 将全部成交单从挂单列表删除
                    elif dict_args['Order']['OrderStatus'] == '1':  # 部分成交还在队列中
                        # i = dict_args['Order']  # 更新挂单列表
                        self.__list_order_pending[i] = dict_args['Order']  # 更新挂单列表
                        if Utils.Strategy_print:
                            print("Strategy.update_list_order_pending() 报单状态：部分成交还在队列中")
                    elif dict_args['Order']['OrderStatus'] == '2':  # 部分成交不在队列中
                        if Utils.Strategy_print:
                            print("Strategy.update_list_order_pending() 报单状态：部分成交不在队列中")
                    elif dict_args['Order']['OrderStatus'] == '3':  # 未成交还在队列中
                        # i = dict_args['Order']  # 更新挂单列表
                        self.__list_order_pending[i] = dict_args['Order']  # 更新挂单列表
                        if Utils.Strategy_print:
                            print("Strategy.update_list_order_pending() 报单状态：未成交还在队列中")
                    elif dict_args['Order']['OrderStatus'] == '4':  # 未成交不在队列中
                        if Utils.Strategy_print:
                            print("Strategy.update_list_order_pending() 报单状态：未成交不在队列中")
                    elif dict_args['Order']['OrderStatus'] == '5':  # 撤单
                        if Utils.Strategy_print:
                            print("Strategy.update_list_order_pending() 报单状态：撤单，合约：", dict_args['Order']['InstrumentID'])
                        self.__list_order_pending.remove(self.__list_order_pending[i])  # 将全部成交单从挂单列表删除
                    elif dict_args['Order']['OrderStatus'] == 'a':  # 未知
                        if Utils.Strategy_print:
                            print("Strategy.update_list_order_pending() 报单状态：未知")
                    elif dict_args['Order']['OrderStatus'] == 'b':  # 尚未触发
                        if Utils.Strategy_print:
                            print("Strategy.update_list_order_pending() 报单状态：尚未触发")
                    elif dict_args['Order']['OrderStatus'] == 'c':  # 已触发
                        if Utils.Strategy_print:
                            print("Strategy.update_list_order_pending() 报单状态：已触发")
                    if Utils.Strategy_print:
                        print("Strategy.update_list_order_pending() 更新后self.__list_order_pending=", self.__list_order_pending)
                    return
            # 挂单列表中找不到对应的OrderRef记录时，新添加挂单到self.__list_order_pending
            if dict_args['Order']['OrderStatus'] in ['1', '3']:
                self.__list_order_pending.append(dict_args['Order'])
                if Utils.Strategy_print:
                    print("Strategy.update_list_order_pending() 报单状态：部分成交还在队列中，未成交还在队列中")
        if Utils.Strategy_print:
            print("Strategy.update_list_order_pending() 更新后self.__list_order_pending=", self.__list_order_pending)

    # 更新任务状态
    def update_task_status(self):
        # if Utils.Strategy_print:
        #     print("Strategy.update_task_status() 更新前self.__trade_tasking=", self.__trade_tasking)
        if self.__position_a_buy_today == self.__position_b_sell_today \
                and self.__position_a_buy_yesterday == self.__position_b_sell_yesterday \
                and self.__position_a_sell_today == self.__position_b_buy_today \
                and self.__position_a_sell_yesterday == self.__position_b_buy_yesterday \
                and len(self.__list_order_pending) == 0:
            self.__trade_tasking = False
        else:
            self.__trade_tasking = True
        # if Utils.Strategy_print:
        #     print("Strategy.update_task_status() 更新后self.__trade_tasking=", self.__trade_tasking)

    """
    # 更新持仓量变量，共12个变量
    def update_position(self, dict_args):
        if Utils.Strategy_print:
            print("Strategy.update_position() 更新持仓量:")
        # A成交
        if dict_args['Order']['InstrumentID'] == self.__list_instrument_id[0]:
            if dict_args['Order']['CombOffsetFlag'] == '0':  # A开仓成交回报
                if dict_args['Order']['Direction'] == '0':  # A买开仓成交回报
                    self.__position_a_buy_today += dict_args['Order']['VolumeTraded']  # 更新持仓
                elif dict_args['Order']['Direction'] == '1':  # A卖开仓成交回报
                    self.__position_a_sell_today += dict_args['Order']['VolumeTraded']  # 更新持仓
            elif dict_args['Order']['CombOffsetFlag'] == '3':  # A平今成交回报
                if dict_args['Order']['Direction'] == '0':  # A买平今成交回报
                    self.__position_a_sell_today -= dict_args['Order']['VolumeTraded']  # 更新持仓
                elif dict_args['Order']['Direction'] == '1':  # A卖平今成交回报
                    self.__position_a_buy_today -= dict_args['Order']['VolumeTraded']  # 更新持仓
            elif dict_args['Order']['CombOffsetFlag'] == '4':  # A平昨成交回报
                if dict_args['Order']['Direction'] == '0':  # A买平昨成交回报
                    self.__position_a_sell_yesterday -= dict_args['Order']['VolumeTraded']  # 更新持仓
                elif dict_args['Order']['Direction'] == '1':  # A卖平昨成交回报
                    self.__position_a_buy_yesterday -= dict_args['Order']['VolumeTraded']  # 更新持仓
            self.__position_a_buy = self.__position_a_buy_today + self.__position_a_buy_yesterday
            self.__position_a_sell = self.__position_a_sell_today + self.__position_a_sell_yesterday
        # B成交
        elif dict_args['Order']['InstrumentID'] == self.__list_instrument_id[1]:
            if dict_args['Order']['CombOffsetFlag'] == '0':  # B开仓成交回报
                if dict_args['Order']['Direction'] == '0':  # B买开仓成交回报
                    self.__position_b_buy_today += dict_args['Order']['VolumeTraded']  # 更新持仓
                elif dict_args['Order']['Direction'] == '1':  # B卖开仓成交回报
                    self.__position_b_sell_today += dict_args['Order']['VolumeTraded']  # 更新持仓
            elif dict_args['Order']['CombOffsetFlag'] == '3':  # B平今成交回报
                if dict_args['Order']['Direction'] == '0':  # B买平今成交回报
                    self.__position_b_sell_today -= dict_args['Order']['VolumeTraded']  # 更新持仓
                elif dict_args['Order']['Direction'] == '1':  # B卖平今成交回报
                    self.__position_b_buy_today -= dict_args['Order']['VolumeTraded']  # 更新持仓
            elif dict_args['Order']['CombOffsetFlag'] == '4':  # B平昨成交回报
                if dict_args['Order']['Direction'] == '0':  # B买平昨成交回报
                    self.__position_b_sell_yesterday -= dict_args['Order']['VolumeTraded']  # 更新持仓
                elif dict_args['Order']['Direction'] == '1':  # B卖平昨成交回报
                    self.__position_b_buy_yesterday -= dict_args['Order']['VolumeTraded']  # 更新持仓
            self.__position_b_buy = self.__position_b_buy_today + self.__position_b_buy_yesterday
            self.__position_b_sell = self.__position_b_sell_today + self.__position_b_sell_yesterday
        if Utils.Strategy_print:
            print("     B合约：今买、昨买、总买", self.__position_b_buy_today, self.__position_b_buy_yesterday, self.__position_b_buy, "今卖、昨卖、总卖", self.__position_b_sell_today, self.__position_b_sell_yesterday, self.__position_b_sell)
        if Utils.Strategy_print:
            print("     A合约：今买、昨买、总买", self.__position_a_buy_today, self.__position_a_buy_yesterday, self.__position_a_buy, "今卖、昨卖、总卖", self.__position_a_sell_today, self.__position_a_sell_yesterday, self.__position_a_sell)
    """
    
    # 更新持仓量变量，共12个变量
    def update_position(self, Trade):
        if Utils.Strategy_print:
            print("Strategy.update_position() 更新持仓量:")
        # A成交
        if Trade['InstrumentID'] == self.__list_instrument_id[0]:
            if Trade['OffsetFlag'] == '0':  # A开仓成交回报
                if Trade['Direction'] == '0':  # A买开仓成交回报
                    self.__position_a_buy_today += Trade['Volume']  # 更新持仓
                elif Trade['Direction'] == '1':  # A卖开仓成交回报
                    self.__position_a_sell_today += Trade['Volume']  # 更新持仓
            elif Trade['OffsetFlag'] == '3':  # A平今成交回报
                if Trade['Direction'] == '0':  # A买平今成交回报
                    self.__position_a_sell_today -= Trade['Volume']  # 更新持仓
                elif Trade['Direction'] == '1':  # A卖平今成交回报
                    self.__position_a_buy_today -= Trade['Volume']  # 更新持仓
            elif Trade['OffsetFlag'] == '4':  # A平昨成交回报
                if Trade['Direction'] == '0':  # A买平昨成交回报
                    self.__position_a_sell_yesterday -= Trade['Volume']  # 更新持仓
                elif Trade['Direction'] == '1':  # A卖平昨成交回报
                    self.__position_a_buy_yesterday -= Trade['Volume']  # 更新持仓
            self.__position_a_buy = self.__position_a_buy_today + self.__position_a_buy_yesterday
            self.__position_a_sell = self.__position_a_sell_today + self.__position_a_sell_yesterday
        # B成交
        elif Trade['InstrumentID'] == self.__list_instrument_id[1]:
            if Trade['OffsetFlag'] == '0':  # B开仓成交回报
                if Trade['Direction'] == '0':  # B买开仓成交回报
                    self.__position_b_buy_today += Trade['Volume']  # 更新持仓
                elif Trade['Direction'] == '1':  # B卖开仓成交回报
                    self.__position_b_sell_today += Trade['Volume']  # 更新持仓
            elif Trade['OffsetFlag'] == '3':  # B平今成交回报
                if Trade['Direction'] == '0':  # B买平今成交回报
                    self.__position_b_sell_today -= Trade['Volume']  # 更新持仓
                elif Trade['Direction'] == '1':  # B卖平今成交回报
                    self.__position_b_buy_today -= Trade['Volume']  # 更新持仓
            elif Trade['OffsetFlag'] == '4':  # B平昨成交回报
                if Trade['Direction'] == '0':  # B买平昨成交回报
                    self.__position_b_sell_yesterday -= Trade['Volume']  # 更新持仓
                elif Trade['Direction'] == '1':  # B卖平昨成交回报
                    self.__position_b_buy_yesterday -= Trade['Volume']  # 更新持仓
            self.__position_b_buy = self.__position_b_buy_today + self.__position_b_buy_yesterday
            self.__position_b_sell = self.__position_b_sell_today + self.__position_b_sell_yesterday
        if Utils.Strategy_print:
            print("     A合约", self.__list_instrument_id[0], "今买、昨买、总买", self.__position_a_buy_today, self.__position_a_buy_yesterday,
                  self.__position_a_buy, "今卖、昨卖、总卖", self.__position_a_sell_today, self.__position_a_sell_yesterday,
                  self.__position_a_sell)
            print("     B合约", self.__list_instrument_id[1], "今买、昨买、总买", self.__position_b_buy_today, self.__position_b_buy_yesterday,
                  self.__position_b_buy, "今卖、昨卖、总卖", self.__position_b_sell_today, self.__position_b_sell_yesterday,
                  self.__position_b_sell)

    # 更新持仓明细list
    def update_list_position_detail(self, input_trade):
        trade = copy.deepcopy(input_trade)  # 形参深度拷贝到方法局部变量，目的是修改局部变量值不会影响到形参
        # 开仓单，添加到list，添加到list尾部
        if trade['OffsetFlag'] == '0':
            self.__list_position_detail.append(trade)
        # 平仓单，先开先平的原则从list里删除
        elif trade['OffsetFlag'] == '1':
            # 遍历self.__list_position_detail
            for i in range(len(self.__list_position_detail)):
                # trade中"OffsetFlag"为平今
                if trade['OffsetFlag'] == '3':
                    if self.__list_position_detail[i]['TradingDay'] == self.__TradingDay\
                            and trade['InstrumentID'] == self.__list_position_detail[i]['InstrumentID'] \
                            and trade['HedgeFlag'] == self.__list_position_detail[i]['HedgeFlag']\
                            and trade['Direction'] != self.__list_position_detail[i]['Direction']:
                            # list_position_detail中的交易日是当前交易日
                            # trade和list_position_detail中的合约代码相同
                            # trade和list_position_detail中的投保标志相同
                            # trade和list_position_detail中的买卖不同
                        # trade中的volume等于持仓明细列表中的volume
                        if trade['Volume'] == self.__list_position_detail[i]['Volume']:
                            del self.__list_position_detail[i]
                        # trade中的volume小于持仓明细列表中的volume
                        elif trade['Volume'] < self.__list_position_detail[i]['Volume']:
                            self.__list_position_detail[i]['Volume'] -= trade['Volume']
                        # trade中的volume大于持仓明细列表中的volume
                        elif trade['Volume'] > self.__list_position_detail[i]['Volume']:
                            trade['Volume'] -= self.__list_position_detail[i]['Volume']
                            del self.__list_position_detail[i]
                # trade中"OffsetFlag"为平昨
                elif trade['OffsetFlag'] == '4':
                    if self.__list_position_detail[i]['TradingDay'] != self.__TradingDay \
                            and trade['InstrumentID'] == self.__list_position_detail[i]['InstrumentID'] \
                            and trade['HedgeFlag'] == self.__list_position_detail[i]['HedgeFlag'] \
                            and trade['Direction'] != self.__list_position_detail[i]['Direction']:
                        # list_position_detail中的交易日不是当前交易日
                        # trade和list_position_detail中的合约代码相同
                        # trade和list_position_detail中的投保标志相同
                        # trade和list_position_detail中的买卖不同
                        # trade中的volume等于持仓明细列表中的volume
                        if trade['Volume'] == self.__list_position_detail[i]['Volume']:
                            del self.__list_position_detail[i]
                        # trade中的volume小于持仓明细列表中的volume
                        elif trade['Volume'] < self.__list_position_detail[i]['Volume']:
                            self.__list_position_detail[i]['Volume'] -= trade['Volume']
                        # trade中的volume大于持仓明细列表中的volume
                        elif trade['Volume'] > self.__list_position_detail[i]['Volume']:
                            trade['Volume'] -= self.__list_position_detail[i]['Volume']
                            del self.__list_position_detail[i]

    # 统计指标
    def statistics(self):
        # 以一天的盘面为周期的统计指标
        # self.__today_profit = dict_args['today_profit']  # 平仓盈利
        # self.__today_commission = dict_args['today_commission']  # 手续费
        # self.__today_trade_volume = dict_args['commission']  # 成交量
        # self.__today_sum_slippage = dict_args['today_sum_slippage']  # 总滑价
        # self.__today_average_slippage = dict_args['today_average_slippage']  # 平均滑价
        #
        # self.__position_a_buy_today = dict_args['position_a_buy_today']  # A合约买持仓今仓
        # self.__position_a_buy_yesterday = dict_args['position_a_buy_yesterday']  # A合约买持仓昨仓
        # self.__position_a_buy = dict_args['position_a_buy']  # A合约买持仓总仓位
        # self.__position_a_sell_today = dict_args['position_a_sell_today']  # A合约卖持仓今仓
        # self.__position_a_sell_yesterday = dict_args['position_a_sell_yesterday']  # A合约卖持仓昨仓
        # self.__position_a_sell = dict_args['position_a_sell']  # A合约卖持仓总仓位
        # self.__position_b_buy_today = dict_args['position_b_buy_today']  # B合约买持仓今仓
        # self.__position_b_buy_yesterday = dict_args['position_b_buy_yesterday']  # B合约买持仓昨仓
        # self.__position_b_buy = dict_args['position_b_buy']  # B合约买持仓总仓位
        # self.__position_b_sell_today = dict_args['position_b_sell_today']  # B合约卖持仓今仓
        # self.__position_b_sell_yesterday = dict_args['position_b_sell_yesterday']  # B合约卖持仓昨仓
        # self.__position_b_sell = dict_args['position_b_sell']  # B合约卖持仓总仓位
        pass

if __name__ == '__main__':
    # df1 = pd.read_csv('D:/CTP_Dev/CTP数据样本/API查询/063802_第1次（启动时流文件为空）/063802_QryTrade.csv', header=0)
    # s = df1['OrderRef'].astype(str).str[-1:].astype(int)
    # df1['StrategyID'] = s
    # df2 = df1[df1.StrategyID == 11]
    # print(df1)

    # 初始化今仓
    """
    self.__user.get_dfQryTrade() 替换为 get_dfQryTrade
    self.__dfQryTrade 替换为 self_dfQryTrade
    self.__dfQryTradeStrategy 替换为 self_dfQryTradeStrategy
    """
    get_dfQryTrade = pd.read_csv('D:/CTP_Dev/CTP数据样本/API查询/063802_第1次（启动时流文件为空）/063802_QryTrade.csv', header=0)
    get_dfQryTrade['StrategyID'] = get_dfQryTrade['OrderRef'].astype(str).str[-2:].astype(
        int)  # 截取OrderRef后两位数为StrategyID
    # print("get_dfQryTrade\n", get_dfQryTrade)