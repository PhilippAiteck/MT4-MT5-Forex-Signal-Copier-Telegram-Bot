#!/usr/bin/env python3
import asyncio
import logging
import math
import os
import re
import json
import requests
import pandas as pd

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

from datetime import datetime, timedelta

from metaapi_cloud_sdk import MetaApi
from openpyxl import load_workbook
from prettytable import PrettyTable
from telegram import ParseMode, Update
from telegram.ext import CommandHandler, Filters, MessageHandler, Updater, ConversationHandler, CallbackContext
from dotenv import load_dotenv

load_dotenv()  # Charge les variables depuis .env

# MetaAPI Credentials
API_KEY = os.environ.get("API_KEY")
ACCOUNT_ID = os.environ.get("ACCOUNT_ID")

# Telegram Credentials
TOKEN = os.environ.get("TOKEN")
TELEGRAM_USER = os.environ.get("TELEGRAM_USER")

# Heroku Credentials
APP_URL = os.environ.get("APP_URL")

# Port number for Telegram bot web hook
PORT = os.environ.get("PORT")

# RISK FACTOR
RISK_FACTOR = float(os.environ.get("RISK_FACTOR"))

# Enables logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# possibles states for conversation handler
CALCULATE, TRADE, DECISION = range(3)

# allowed FX symbols
ENERGIES = ['USOIL', 'UKOIL', 'USOUSD', 'UKOUSD', 'XNGUSD', 'CL-OIL']
METAUX = ['XAUUSD', 'XAUEUR', 'XAUGBP', 'XAGUSD', 'XAGEUR', 'XAGGBP', 'XPTUSD', 'XPTEUR', 'XPTGBP', 'XPDEUR', 'XPDGBP', 'GOLD']
INDICES = ['SPX500', 'US500', 'US30', 'DJ30', 'USTEC', 'USTECH', 'NAS100', 'NDX100', 'US100', 'DE30', 'GER30', 'UK100', 'AUS200', 'FR40', 'FRA40', 'JP225', 'JPN225', 'HK50', 'IN50', 'CN50', 'SG30', 'STOXX50']
CRYPTO = ['BTCUSD', 'ETHUSD', 'XRPUSD', 'LTCUSD', 'BCHUSD', 'ADAUSD', 'XLMUSD', 'EOSUSD', 'XMRUSD', 'DASHUSD', 'ZECUSD', 'BNBUSD', 'XTZUSD', 'ATOMUSD', 'ONTUSD', 'NEOUSD', 'VETUSD', 'ICXUSD', 'QTUMUSD', 'ZRXUSD', 'DOGEUSD', 'LINKUSD', 'HTUSD', 'ETCUSD', 'OMGUSD', 'NANOUSD', 'LSKUSD', 'WAVESUSD', 'REPUSD', 'MKRUSD', 'GNTUSD', 'LOOMUSD', 'MANAUSD', 'KNCUSD', 'CVCUSD', 'BATUSD', 'NEXOUSD', 'DCRUSD', 'PAXUSD', 'TUSDUSD', 'USDCUSD', 'USDTUSD']
FOREX = ['EURUSD', 'USDJPY', 'GBPUSD', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY', 'AUDJPY', 'NZDJPY', 'EURAUD', 'GBPAUD', 'EURNZD', 'GBPNZD', 'EURCAD', 'GBPCAD', 'AUDCAD', 'NZDCAD', 'EURCHF', 'GBPCHF', 'AUDCHF', 'NZDCHF', 'USDBRL',  'USDSEK', 'USDDKK', 'USDNOK', 'USDTRY', 'USDMXN', 'USDZAR', 'EURSEK', 'EURDKK', 'EURNOK', 'EURTRY', 'EURMXN', 'EURZAR', 'GBPSEK', 'GBPDKK', 'GBPNOK', 'GBPTRY', 'GBPMXN', 'GBPZAR', 'AUDSEK', 'AUDDKK', 'AUDNOK', 'AUDTRY', 'AUDMXN', 'AUDZAR', 'CADJPY', 'AUDNZD', 'CHFJPY']

# Variable temporaire pour stocker le taux de change
exchange_rate = None

# Helper Functions
def ParseSignal(signal: str) -> dict:
    """Starts process of parsing signal and entering trade on MetaTrader account.

    Arguments:
        signal: trading signal

    Returns:
        a dictionary that contains trade signal information
    """

    # converts message to list of strings for parsing
    signal = signal.splitlines()
    signal = [line.rstrip() for line in signal]
    #signal = re.sub(r'\s+', ' ', signale)
    
    trade = {}

    if len(signal) < 3 :
        if('METTRE LE'.lower() in signal[0].lower()):
            # extract the Stop
            trade['newstop'] = float(((signal[0].split())[4]) + ((signal[0].split())[5]))
        elif('SL'.lower() in signal[0].lower() and 'TP'.lower() in signal[0].lower()):
            # extract the Stop
            trade['newstop'] = ''
            trade['new_sl'] = float(((signal[0].split())[1]))
            trade['new_tp'] = float(((signal[0].split())[3]))
            if len(signal[0].split()) == 6:
                trade['trade_id'] = ''
                trade['ordertype'] = (signal[0].split())[4]
                trade['symbol'] = (signal[0].split())[5]
            elif len(signal[0].split()) == 5:
                if (signal[0].split())[4] == 'BUY' or (signal[0].split())[4] == 'SELL':
                    trade['trade_id'] = ''
                    trade['ordertype'] = (signal[0].split())[4]
                    trade['symbol'] = ''
                else:
                    trade['trade_id'] = ''
                    trade['ordertype'] = ''
                    trade['symbol'] = (signal[0].split())[4]
            else:
                trade['trade_id'] = ''
                trade['symbol'] = ''
                trade['ordertype'] = ''
            #trade['ordertype'] = (signal[0].split())[-3]
        elif('SL'.lower() in signal[0].lower() or 'TP'.lower() in signal[0].lower()):
            # extract the Stop
            trade['newstop'] = float(((signal[0].split())[1]))
            trade['new_sl'] = ''
            trade['new_tp'] = ''
            if len(signal[0].split()) == 4:
                trade['trade_id'] = ''
                trade['ordertype'] = (signal[0].split())[2]
                trade['symbol'] = (signal[0].split())[3]
            elif len(signal[0].split()) == 3:
                if (signal[0].split())[2] == 'BUY' or (signal[0].split())[2] == 'SELL':
                    trade['trade_id'] = ''
                    trade['ordertype'] = (signal[0].split())[2]
                    trade['symbol'] = ''
                else:
                    trade['trade_id'] = ''
                    trade['ordertype'] = ''
                    trade['symbol'] = (signal[0].split())[2]
            else:
                trade['trade_id'] = ''
                trade['symbol'] = ''
                trade['ordertype'] = ''
            #trade['ordertype'] = (signal[0].split())[-3]
        elif('CLORES' in signal[0] or 'BRV' in signal[0]):
            if len(signal[0].split()) == 3:
                trade['trade_id'] = ''
                trade['ordertype'] = (signal[0].split())[1]
                trade['symbol'] = (signal[0].split())[2]
            elif len(signal[0].split()) == 2:
                if (signal[0].split())[1] == 'BUY' or (signal[0].split())[1] == 'SELL':
                    trade['trade_id'] = ''
                    trade['ordertype'] = (signal[0].split())[1]
                    trade['symbol'] = ''
                else:
                    trade['trade_id'] = ''
                    trade['ordertype'] = ''
                    trade['symbol'] = (signal[0].split())[1]
            else:
                trade['trade_id'] = ''
                trade['symbol'] = ''
                trade['ordertype'] = ''
        elif('PARTIELS' in signal[0]):
            trade['pourcentage'] = float(((signal[0].split())[1]))
            if len(signal[0].split()) == 4:
                trade['trade_id'] = ''
                trade['ordertype'] = (signal[0].split())[2]
                trade['symbol'] = (signal[0].split())[3]
            elif len(signal[0].split()) == 3:
                if (signal[0].split())[2] == 'BUY' or (signal[0].split())[2] == 'SELL':
                    trade['trade_id'] = ''
                    trade['ordertype'] = (signal[0].split())[2]
                    trade['symbol'] = ''
                else:
                    trade['trade_id'] = ''
                    trade['ordertype'] = ''
                    trade['symbol'] = (signal[0].split())[2]
            else:
                trade['trade_id'] = ''
                trade['symbol'] = ''
                trade['ordertype'] = ''
        elif('BE' in signal[0] or 'CLORE' in signal[0] or 'PARTIEL' in signal[0]):
            if (signal[0].split())[0] == 'PARTIEL':
                trade['pourcentage'] = float(((signal[0].split())[1]))
            trade['trade_id'] = (signal[0].split())[-1]
            #trade['symbol'] = ''

    else:
        # determines the order type of the trade
        if('buy limit' in signal[0].lower()):
            trade['OrderType'] = 'Buy Limit'

        elif('sell limit' in signal[0].lower()):
            trade['OrderType'] = 'Sell Limit'

        elif('buy stop' in signal[0].lower()):
            trade['OrderType'] = 'Buy Stop'

        elif('sell stop' in signal[0].lower()):
            trade['OrderType'] = 'Sell Stop'

        elif('buy' in signal[0].lower()):
            trade['OrderType'] = 'Buy'

        elif('achète' in signal[0].lower()):
            trade['OrderType'] = 'ACHAT'
        
        elif('sell' in signal[0].lower()):
            trade['OrderType'] = 'Sell'

        elif('vends' in signal[0].lower()):
            trade['OrderType'] = 'VENTE'
        
        # returns an empty dictionary if an invalid order type was given
        else:
            return {}
        
        # checks if the symbol is valid, if not, returns an empty dictionary
        #if((trade['Symbol'] not in SYMBOLS) and (trade['Symbol'] not in SPECIALSYMBOLS)):
        #    return {}
        
        # checks wheter or not to convert entry to float because of market exectution option ("NOW")
        #if(trade['OrderType'] == 'Buy' or trade['OrderType'] == 'Sell'):
        #    trade['Entry'] = (signal[1].split())[-1]

        # checks if it's market exectution option ACHAT or VENTE to extract null: PE, SL and TP
        if(trade['OrderType'] == 'ACHAT' or trade['OrderType'] == 'VENTE'):
            trade['Symbol'] = (signal[0].split())[-1]
            if('(' in trade['Symbol'] or ')' in trade['Symbol']):
                trade['Symbol'] = (signal[0].split())[-2]
            #trade['Symbol'] = trade['Symbol'].replace('/','')
            #trade['Symbol'] = trade['Symbol']+"m"
            trade['Entry'] = (signal[2].split(' : '))[-1].replace(' ','')
            trade['Entry'] = float((trade['Entry'].split('-'))[0])

            #trade['StopLoss'] = 0
            #trade['TP'] = [0, 0, 0]

            if(trade['OrderType'] == 'ACHAT'):
                if(len(signal) > 7 and 'TP1'.lower() in signal[6].lower()):
                    trade['TP'] = [float(signal[6].split(' : ')[-1].replace(' ','')), float(signal[7].split(':')[-1].replace(' ','')), trade['Entry'] + 3000]
                    trade['StopLoss'] = float((signal[10].replace('🔒','').replace(' ','').split(':'))[-1])
                else:
                    trade['TP'] = [trade['Entry'] + 600, trade['Entry'] + 1200, trade['Entry'] + 3000]
                    trade['StopLoss'] = float((signal[6].replace('🔒','').replace(' ','').split(':'))[-1])

            if(trade['OrderType'] == 'VENTE'):
                if(len(signal) > 7 and 'TP1'.lower() in signal[6].lower()):
                    trade['TP'] = [float(signal[6].split(' : ')[-1].replace(' ','')), float(signal[7].split(':')[-1].replace(' ','')), trade['Entry'] - 3000]
                    trade['StopLoss'] = float((signal[10].replace('🔒','').replace(' ','').split(':'))[-1])
                else:
                    trade['TP'] = [trade['Entry'] - 600, trade['Entry'] - 1200, trade['Entry'] - 3000]
                    trade['StopLoss'] = float((signal[6].replace('🔒','').replace(' ','').split(':'))[-1])

        else:
            
            if('🔽' in signal[0] or '🔼' in signal[0]):
                trade['Symbol'] = (signal[0].split())[0][1:]
                trade['Entry'] = float((signal[0].split())[-1])
                trade['TP'] = [float((signal[2].replace(' ','').split(':'))[-1])]
                # checks if there's a TP2 and parses it
                if('tp' in signal[3].lower()):
                    trade['TP'].append(float(signal[3].replace(' ','').split(':')[-1]))
                    trade['StopLoss'] = float((signal[5].replace(' ','').split(':'))[-1])
                else:
                    trade['StopLoss'] = float((signal[4].replace(' ','').split(':'))[-1])
                
                if(len(signal) > 6 and 'RISK'.lower() in signal[6].lower()):
                    trade['RiskFactor'] = float((signal[6].split())[-1])
                else:
                    trade['RiskFactor'] = RISK_FACTOR

            elif(',' in signal[2].lower()):
                # ✅ Extraction des données du signal
                order_info = signal[0].split()
                order_type = order_info[0].upper()  # BUY ou SELL
                symbol = order_info[1].upper()  # EURAUD, BTCUSD, XAUUSD...
                entry_low = float(order_info[2])  # 1.6650
                entry_high = float(order_info[3])  # 1.6680
                stop_loss = float(signal[1])  # 1.66900
                tp_pips = list(map(int, signal[2].split(",")))  # [30, 50, 100]

                # ✅ Détection automatique du tick_size
                if symbol in CRYPTO:
                    tick_size = 10
                elif symbol in INDICES:
                    tick_size = 1
                elif symbol in ["XAUUSD", "XAUEUR", "XAUGBP"]:
                    tick_size = 0.1
                elif symbol in ["XAGUSD", "XAGEUR", "XAGGBP"]:
                    tick_size = 0.001
                elif "JPY" in symbol or len(str(entry_low).split(".")[1]) == 2:
                    tick_size = 0.01
                else:
                    tick_size = 0.0001

                # ✅ Calcul automatique de l'espacement entre les ordres limits
                num_orders = 9  # Nombre total d'ordres
                order_spacing = round((entry_high - entry_low) / (num_orders - 1), 5)

                # ✅ Génération des niveaux de pending orders
                order_limits = [round(entry_low + i * order_spacing, 5) for i in range(num_orders)]

                # ✅ Calcul des niveaux TP en fonction du premier ordre limit
                base_tp = entry_low - tp_pips[0] * tick_size if order_type == "SELL" else entry_low + tp_pips[0] * tick_size

                tp_levels = {
                    "TP1": [round(base_tp, 5)] * 4,  # 4 premiers ordres
                    "TP2": [round(base_tp - (tp_pips[1] - tp_pips[0]) * tick_size, 5)] * 3,  # 3 suivants
                    "TP3": [round(base_tp - (tp_pips[2] - tp_pips[0]) * tick_size, 5)] * 2  # 2 derniers
                }

                # ✅ Construction du dictionnaire final
                trade = {
                    "OrderType": "Sell Limits" if order_type == "SELL" else "Buy Limits",
                    "Symbol": symbol,
                    "Entry": order_limits,
                    "StopLoss": stop_loss,
                    "TP": tp_levels["TP1"] + tp_levels["TP2"] + tp_levels["TP3"],
                    "RiskFactor": float(signal[3].split()[0])
                }
                
                trade["Symbol"] = symbol
                trade["Entry"] = order_limits
                trade['StopLoss'] = stop_loss  # 1.6690
                trade['RiskFactor'] = float((signal[3].split())[0])

                # ✅ Affichage du résultat
                #print(trade)


                    # ✅ Génération de la liste des ordres
                    #orders = []
                    #trade['TP'] = []
                    #for i, order_price in enumerate(order_limits):
                        #tp_level = (
                            #trade['TP'].append(float(tp_levels["TP1"][i])) if i < 4 else 
                            #trade['TP'].append(float(tp_levels["TP2"][i - 4])) if i < 7 else 
                            #trade['TP'].append(float(tp_levels["TP3"][i - 7])) 
                        #)
                        
                        #orders.append({
                            #"symbol": symbol,
                            #"type": order_type + " LIMIT",
                            #"entry": order_price,
                            #"stop_loss": stop_loss,
                            #"take_profit": tp_level
                        #})

                    # ✅ Affichage des ordres générés
                    #for order in orders:
                        #print(order)





            elif('-' in signal[0].lower()):
                trade['Symbol'] = (signal[0].split())[1]
                trade['Entry'] = (signal[0].split('@'))[-1]
                trade['Entry'] = [float((trade['Entry'].split('-'))[0])]
                trade['Entry'].append(float((signal[0].split('-'))[-1]))

                order_limits_spacing = 0.5
                order_limits = []  # Liste pour stocker les niveaux d'ordre Limit
                current_price = trade["Entry"][0]
                # Création des niveaux d'ordre Limit
                if trade['OrderType'] == 'Buy':
                    trade['OrderType'] = 'Buy Limits'
                    while current_price >= trade["Entry"][1]:
                        order_limits.append(current_price)
                        current_price -= order_limits_spacing
                else:
                    trade['OrderType'] = 'Sell Limits'
                    while current_price <= trade["Entry"][1]:
                        order_limits.append(current_price)
                        current_price += order_limits_spacing

                trade["Entry"] = order_limits
                trade['StopLoss'] = float((signal[2].replace(' ','').split(':'))[-1])
                trade['TP'] = [float((signal[4].replace(' ','').split(':'))[-1])]
                trade['TP'].append(float((signal[5].replace(' ','').split(':'))[-1]))

                take_profits = []
                # Les 4 premiers ordre limits pour TP1
                for i in range(4):
                    take_profits.append(trade['TP'][0])
                # Les 3 suivants pour TP2
                for i in range(4, 7):
                    take_profits.append(trade['TP'][1])
                # Les 2 derniers n'ont pas de TP
                for i in range(7, 9):
                    if 'Buy' in trade['OrderType']:
                        take_profits.append(trade['TP'][1]+11)
                    else:
                        take_profits.append(trade['TP'][1]-11)

                trade['TP'] = take_profits
                trade['RiskFactor'] = float((signal[7].split())[-1])


            elif('TP'.lower() in signal[1].lower() or 'TP'.lower() in signal[2].lower()):
                trade['Symbol'] = (signal[0].split())[0]
                #trade['Entry'] = (signal[0].split())[-1]
                #trade['Entry'] = float(signal[0].replace(' ','').split('@')[-1])
                if('@' in (signal[0].split())[-1]):
                    trade['Entry'] = float(signal[0].replace(' ','').split('@')[-1])
                else:
                    trade['Entry'] = float((signal[0].split())[-1])
                if ('LIMIT'.lower() in signal[1].lower()):
                    trade['TP'] = [float((signal[2].replace(' ','').split('@'))[-1])]
                    trade['TP'].append(float(signal[3].replace(' ','').split('@')[-1]))
                    trade['TP'].append(float(signal[4].replace(' ','').split('@')[-1]))
                    trade['StopLoss'] = float((signal[6].replace(' ','').split('@'))[-1])
                    if(len(signal) > 7 and 'RISK'.lower() in signal[7].lower()):
                        trade['RiskFactor'] = float((signal[7].split())[-1])
                    else:
                        trade['RiskFactor'] = RISK_FACTOR
                else:
                    trade['TP'] = [float((signal[1].replace(' ','').split('@'))[-1])]
                    trade['TP'].append(float(signal[2].replace(' ','').split('@')[-1]))
                    trade['TP'].append(float(signal[3].replace(' ','').split('@')[-1]))
                    trade['StopLoss'] = float((signal[5].replace(' ','').split('@'))[-1])
                    # checks if there's a TP2 and parses it
                    # if(len(signal) >= 5 and 'tp'.lower() in signal[2].lower()):
                    #     trade['TP'].append(float(signal[2].split()[-1]))
                    #     trade['StopLoss'] = float((signal[4].split())[-1])
                    # else:
                    #     trade['StopLoss'] = float((signal[3].split())[-1])
                    if(len(signal) > 6 and 'RISK'.lower() in signal[6].lower()):
                        trade['RiskFactor'] = float((signal[6].split())[-1])
                    else:
                        trade['RiskFactor'] = RISK_FACTOR

 
            elif('SL'.lower() in signal[2].lower()):
                if('limit'.lower() in trade['OrderType'].lower()):
                    if('for'.lower() in signal[0].lower()):
                        trade['Symbol'] = (signal[0].split())[3]
                    else:
                        trade['Symbol'] = (signal[0].split())[0]
                else:
                    trade['Symbol'] = (signal[0].split())[1]

                if('#' in trade['Symbol'] or '@' in trade['Symbol']):
                    trade['Symbol'] = trade['Symbol'][1:]
                if('-' in trade['Symbol']):
                    trade['Symbol'] = trade['Symbol'].replace('-','')
                #if('@' in trade['Entry']):
                #    trade['Symbol'] = (signal[0].split())[1][1:]
                trade['Entry'] = (signal[0].split())[-1]
                if(trade['Entry'].lower() != 'NOW'.lower()):
                    trade['Entry'] = float((signal[0].split())[-1].replace('@',''))
                trade['StopLoss'] = float((signal[2].replace(' ','').split('@'))[-1])
                trade['TP'] = [float((signal[3].replace(' ','').split('@'))[-1])]
                # checks if there's a TP2 and parses it
                if (len(signal) >= 5 and 'Tp'.lower() in signal[4].lower()):
                    trade['TP'].append(float((signal[4].replace(' ','').split('@'))[-1]))
                
                if(len(signal) >= 5 and 'RISK'.lower() in signal[4].lower()):
                    trade['RiskFactor'] = float((signal[4].split())[-1])
                elif(len(signal) >= 6 and 'RISK'.lower() in signal[5].lower()):
                    trade['RiskFactor'] = float((signal[5].split())[-1])
                else:
                    trade['RiskFactor'] = RISK_FACTOR
            

            # elif('@'.lower() in signal[2].lower()):
            #     if len(signal) >= 4:
            #         trade['StopLoss'] = float((signal[2].replace(' ','').split('@'))[-1])
            #         trade['TP'] = [float((signal[3].replace(' ','').split('@'))[-1])]
            #         if len(signal) >= 5 and 'tp' in signal[4].lower():
            #             trade['TP'].append(float((signal[4].replace(' ','').split('@'))[-1]))
                
            #     trade['RiskFactor'] = RISK_FACTOR



        if(trade['Symbol'].lower() == 'GOLD'.lower() or trade['Symbol'].lower() == 'XAUUAD'.lower()): 
            trade['Symbol'] = 'XAUUSD'
   
        # adds risk factor to trade
        #trade['RiskFactor'] = RISK_FACTOR

    #logger.info(trade)

    return trade

def GetTradeInformation(update: Update, trade: dict, balance: float, currency: str, multiplier: float) -> None:
    """Calculates information from given trade including stop loss and take profit in pips, posiition size, and potential loss/profit.

    Arguments:
        update: update from Telegram
        trade: dictionary that stores trade information
        balance: current balance of the MetaTrader account
        currency: currency of the MetaTrader account
    """

    # convertion xof_to_usd
    if currency == 'XOF':
        #if(balance <= 30228):
        #    trade['PositionSize'] = 0.01
        #else:
        # Conversion de XOF en USD
        amount_usd = xof_to_usd(balance)
        balance = amount_usd

    # pips calculation
    takeProfitPips = []
    pips_tp1 = []
    pips_tp2 = []
    pips_tp3 = []
            

    #logger.info(trade['Entry'])
    #logger.info(trade['TP'])

        
    # calculates the stop loss and take profit in pips
    if ('Limits' in trade['OrderType']):
        stopLossPips = []
        logger.info(trade['Entry'])

        for order_limit in trade['Entry']:
            # Le montant à risquer sur chaque trade doit être proportionnel à cette distance
            stopLossPips.append(abs(round((trade['StopLoss'] - order_limit) / multiplier)))

        logger.info(stopLossPips)

        for order_limit in trade['Entry'][:4]:
            # calculates the take profit(s) in pips
            takeProfitPips.append(abs(round((trade['TP'][0] - order_limit) / multiplier)))
        for order_limit in trade['Entry'][4:7]:
            # calculates the take profit(s) in pips
            takeProfitPips.append(abs(round((trade['TP'][4] - order_limit) / multiplier)))
        for order_limit in trade['Entry'][7:]:
            # calculates the take profit(s) in pips
            takeProfitPips.append(abs(round((trade['TP'][7] - order_limit) / multiplier)))

        logger.info(takeProfitPips)

        # Calcul des pips pour TP1
        pips_tp1 = takeProfitPips[:4]

        # Calcul des pips pour TP2
        pips_tp2 = takeProfitPips[4:7]

        # Calcul des pips pour TP3
        pips_tp3 = takeProfitPips[7:]
            
        logger.info(pips_tp1)
        logger.info(pips_tp2)
        logger.info(pips_tp3)

    else:
        stopLossPips = abs(round((trade['StopLoss'] - trade['Entry']) / multiplier))

        logger.info(stopLossPips)

        # calculates the take profit(s) in pips
        for takeProfit in trade['TP']:
            takeProfitPips.append(abs(round((takeProfit - trade['Entry']) / multiplier)))

        logger.info(takeProfitPips)

    
    # calculates the position size
    if(trade['OrderType'] == 'ACHAT' or trade['OrderType'] == 'VENTE'):
        if currency == 'XOF':
            if(balance <= 301571):
                trade['PositionSize'] = 0.06

            elif(balance > 301571 and balance < 604351):
                trade['PositionSize'] = 0.12

            elif(balance > 604351 and balance < 1208702):
                trade['PositionSize'] = 0.24

            elif(balance > 1208702 and balance < 1813054):
                trade['PositionSize'] = 0.27

            elif(balance > 1813054 and balance < 2417405):
                trade['PositionSize'] = 0.30

            elif(balance > 2417405 and balance < 3021757):
                trade['PositionSize'] = 0.33

            elif(balance > 3021757 and balance < 3626108):
                trade['PositionSize'] = 0.36

            elif(balance > 3626108 and balance < 4230459):
                trade['PositionSize'] = 0.39

            else:
                trade['PositionSize'] = 0.42
                
        else:

            if(balance <= 499):
                trade['PositionSize'] = 0.06

            elif(balance > 499 and balance < 1000):
                trade['PositionSize'] = 0.12

            elif(balance > 1000 and balance < 2000):
                trade['PositionSize'] = 0.24

            elif(balance > 2000 and balance < 3000):
                trade['PositionSize'] = 0.27

            elif(balance > 3000 and balance < 4000):
                trade['PositionSize'] = 0.30

            elif(balance > 4000 and balance < 5000):
                trade['PositionSize'] = 0.33

            elif(balance > 5000 and balance < 6000):
                trade['PositionSize'] = 0.36

            elif(balance > 6000 and balance < 7000):
                trade['PositionSize'] = 0.39

            else:
                trade['PositionSize'] = 0.42


    elif 'Limits' in trade['OrderType']:
        trade['PositionSize'] = []
        for order_limit_stopLossPips in stopLossPips:
            # calculates the position size using stop loss and RISK FACTOR
            trade['order_limits_positionsize'] = math.floor((((balance * trade['RiskFactor']) / len(trade['Entry'])) / order_limit_stopLossPips) / 10 * 100) / 100
            # Le montant à risquer sur chaque trade doit être proportionnel à cette distance
            trade['PositionSize'].append(trade['order_limits_positionsize'])
        logger.info(trade['PositionSize'])

    else:
        # calculates the position size using stop loss and RISK FACTOR
        trade['PositionSize'] = math.floor(((balance * trade['RiskFactor']) / stopLossPips) / 10 * 100) / 100


    if(trade['OrderType'] != 'ACHAT' and trade['OrderType'] != 'VENTE' ):
        # creates table with trade information
        table = CreateTable(trade, balance, stopLossPips, takeProfitPips, pips_tp1, pips_tp2, pips_tp3)
        
        # sends user trade information and calcualted risk
        update.effective_message.reply_text(f'<pre>{table}</pre>', parse_mode=ParseMode.HTML)
        

    return

def CreateTable(trade: dict, balance: float, stopLossPips, takeProfitPips, pips_tp1: dict, pips_tp2: dict, pips_tp3: dict) -> PrettyTable:
    """Creates PrettyTable object to display trade information to user.

    Arguments:
        trade: dictionary that stores trade information
        balance: current balance of the MetaTrader account
        stopLossPips: the difference in pips from stop loss price to entry price

    Returns:
        a Pretty Table object that contains trade information
    """

    # creates prettytable object
    table = PrettyTable()
    
    table.title = "Trade Information"
    table.field_names = ["Key", "Value"]
    table.align["Key"] = "l"  
    table.align["Value"] = "l" 

    table.add_row([trade["OrderType"] , trade["Symbol"]])

    if 'Limits' in trade["OrderType"]:
        table.add_row(['Entry\n', trade['Entry'][0]])
        table.add_row(['Stop Loss', '{} pips'.format(sum(stopLossPips))])

        # Affichage des résultats pour TP1
        #table.add_row('\nOrdre Limits avec TP1:')        
        for i, entry_price in enumerate(trade['Entry'][:4]):
            table.add_row([f'Ordre Limit à {entry_price}: TP1 =', f'{pips_tp1[i]} pips'])

        # Affichage des résultats pour TP2
        #table.add_row("\nOrdre Limits avec TP2:")
        for i, entry_price in enumerate(trade['Entry'][4:7]):
            table.add_row([f'Ordre Limit à {entry_price}: TP2 =', f'{pips_tp2[i]} pips'])

        # Affichage des résultats pour TP3
        #table.add_row("\nOrdre Limits avec TP3:")
        for i, entry_price in enumerate(trade['Entry'][7:]):
            table.add_row([f'Ordre Limit à {entry_price}: TP3 =', f'{pips_tp3[i]} pips'])

        table.add_row(['\nRisk Factor', '\n{:,.0f} %'.format(trade['RiskFactor'] * 100)])
        table.add_row(['Position Size', sum(trade['PositionSize'])])
        
        table.add_row(['\nCurrent Balance', '\n$ {:,.2f}'.format(balance)])
        table.add_row(['Potential Loss', '$ {:,.2f}'.format(round(sum([(position_size * 10) * stopLossPips[i] for i, position_size in enumerate(trade['PositionSize'])]), 2))])

    else:
        table.add_row(['Entry\n', trade['Entry']])

        table.add_row(['Stop Loss', '{} pips'.format(stopLossPips)])

        for count, takeProfit in enumerate(takeProfitPips):
            table.add_row([f'TP {count + 1}', f'{takeProfit} pips'])

        table.add_row(['\nRisk Factor', '\n{:,.0f} %'.format(trade['RiskFactor'] * 100)])
        table.add_row(['Position Size', trade['PositionSize']])

        table.add_row(['\nCurrent Balance', '\n$ {:,.2f}'.format(balance)])
        table.add_row(['Potential Loss', '$ {:,.2f}'.format(round((trade['PositionSize'] * 10) * stopLossPips, 2))])


    # total potential profit from trade
    totalProfit = 0
    if 'Limits' in trade["OrderType"]:
        for count, pip_tp1 in enumerate(pips_tp1):
            profit = round((trade['PositionSize'][:4][count] * 10 * (1 / len(pips_tp1))) * pip_tp1, 2)
            table.add_row([f'TP1 Profit', '$ {:,.2f}'.format(profit)])
            
            # sums potential profit from each take profit target
            totalProfit += profit

        #table.add_row(['\nTotal Profit TP1', '\n$ {:,.2f}'.format(totalProfit)])

        for count, pip_tp2 in enumerate(pips_tp2):
            profit = round((trade['PositionSize'][4:7][count] * 10 * (1 / len(pips_tp2))) * pip_tp2, 2)
            table.add_row([f'TP2 Profit', '$ {:,.2f}'.format(profit)])
            
            # sums potential profit from each take profit target
            totalProfit += profit

        #table.add_row(['\nTotal Profit TP2', '\n$ {:,.2f}'.format(totalProfit)])

        for count, pip_tp3 in enumerate(pips_tp3):
            profit = round((trade['PositionSize'][7:][count] * 10 * (1 / len(pips_tp3))) * pip_tp3, 2)
            table.add_row([f'TP3 Profit', '$ {:,.2f}'.format(profit)])
            
            # sums potential profit from each take profit target
            totalProfit += profit

        table.add_row(['\nTotal Profit TP', '\n$ {:,.2f}'.format(totalProfit)])

    else:
        for count, takeProfit in enumerate(takeProfitPips):
            profit = round((trade['PositionSize'] * 10 * (1 / len(takeProfitPips))) * takeProfit, 2)
            table.add_row([f'TP {count + 1} Profit', '$ {:,.2f}'.format(profit)])
            
            # sums potential profit from each take profit target
            totalProfit += profit

        table.add_row(['\nTotal Profit', '\n$ {:,.2f}'.format(totalProfit)])

    return table



async def ConnectCloseTrade(update: Update, context: CallbackContext, trade: dict, trade_id, signalInfos_converted) -> None:
    """Close ongoing trades.

    Arguments:
        update: update from Telegram
    """
    api = MetaApi(API_KEY)
    #update.effective_message.reply_text(signalInfos_converted)

    try:
        account = await api.metatrader_account_api.get_account(ACCOUNT_ID)
        initial_state = account.state
        deployed_states = ['DEPLOYING', 'DEPLOYED']

        if initial_state not in deployed_states:
            #  wait until account is deployed and connected to broker
            logger.info('Deploying account')
            await account.deploy()

        logger.info('Waiting for API server to connect to broker ...')
        await account.wait_connected()

        # connect to MetaApi API
        connection = account.get_rpc_connection()
        await connection.connect()

        # wait until terminal state synchronized to the local state
        logger.info('Waiting for SDK to synchronize to terminal state ...')
        await connection.wait_synchronized()

        # Récupérer la connexion à partir du contexte de l'application
        #connection = context.bot_data['mt_streaming_connection']
        #update.effective_message.reply_text(f"CONNECTION: {connection}")
        
        # Fetch profit of the position
        #position = await connection.get_history_orders_by_position(position_id=trade_id)
        #profit = position['profit']

        # Si le signal est donné sans ID de position
        if not trade_id:
            # Et si le signal n'est pas une reponse
            if update.effective_message.reply_to_message is None:
                # Récuperation de toutes les positions en cours
                #positions = connection.terminal_state.positions
                positions = await connection.get_positions()
                # On boucle dans les resultats "positions"
                for position in positions:
                    # On verifie certaines conditions
                    if (not trade['symbol'] and not trade['ordertype']) \
                        or (position['symbol'] == trade['symbol'] and position['type'].endswith(trade['ordertype'])) \
                        or (not trade['symbol'] and position['type'].endswith(trade['ordertype'])) \
                        or (not trade['ordertype'] and position['symbol'] == trade['symbol']):
                        if 'pourcentage' in trade and trade['pourcentage'] is not None:
                            # Fermer la position partiellement
                            pourcentage_volume = round(float(trade['pourcentage']) / 100 * position['volume'], 2)
                            result = await connection.close_position_partially(position['id'], pourcentage_volume)
                            update.effective_message.reply_text(f"Position {position['id']} > {trade['ordertype']} {position['symbol']} fermée partiellement avec succes.")
                            logger.info(result)
                        else:
                            # On ferme entièrement la ou les position(s) selon les conditions
                            result = await connection.close_position(position['id'])
                            update.effective_message.reply_text(f"Position {position['id']} > {trade['ordertype']} {position['symbol']} fermée avec succes.")
                            logger.info(result)

            else:
                # Sinon le signal est une reponse
                # On récupère l'ID "messageid" du signal source
                messageid = update.effective_message.reply_to_message.message_id
                
                # Précisons qu'apres un signal de trade reçu, chaque ID de position est 
                # récupéré apres l'exécution des trades et enregistré dans le fichier 
                # JSON sérialisé "signalInfos_converted" au format 
                # {"messageid": ["position_id", "position_id", "position_id"], }
                
                # On boucle dans la sous-liste "messageid" recupérer les ID "position_id" 
                for position_id in signalInfos_converted[messageid]:
                    if 'pourcentage' in trade and trade['pourcentage'] is not None:
                        position = await connection.get_position(position_id)
                        # Fermer la position partiellement
                        pourcentage_volume = round(float(trade['pourcentage']) / 100 * position['volume'], 2)
                        result = await connection.close_position_partially(position_id, pourcentage_volume)
                        update.effective_message.reply_text(f"Position {position_id} fermée partiellement avec succes.")
                        logger.info(result)
                    else:
                        # On Ferme ensuite entièrement toutes les positions de la liste
                        result = await connection.close_position(position_id)
                        update.effective_message.reply_text(f"Position {position_id} fermée avec succes.")
                        logger.info(result)

        else:
            # Sinon le signal est un TAKEPROFIT ou une cloture volontaire
            if 'pourcentage' in trade and trade['pourcentage'] is not None:
                position = await connection.get_position(trade_id)
                # Si la position existe ou est en cour d'exécution 
                if position is not None:
                    # Récupération du volume de la position et calcul du pourcentage du volume à fermer
                    pourcentage_volume = round(float(trade['pourcentage']) / 100 * position['volume'], 2)
                    # Fermer la position partiellement
                    result = await connection.close_position_partially(trade_id, pourcentage_volume)
                    update.effective_message.reply_text(f"Position {trade_id} fermée partiellement avec succes.")
                    logger.info(result)
            else:            
                # On ferme donc la position
                result = await connection.close_position(trade_id)
                update.effective_message.reply_text(f"Position {trade_id} fermée avec succes. 💰")
                logger.info(result)

            # Si cest le signal du prémier TAKEPROFIT
            if('TP1'.lower() in update.effective_message.text.lower()):
                # On recupère l'ID "messageid" du signal source
                messageid = update.effective_message.reply_to_message.message_id
                # On boucle dans la sous-liste "messageid" pour recupérer les deux derniers ID  
                for position_id in signalInfos_converted[messageid][1:]:
                    # Récupération des informations sur la position avec "position_id"
                    position = await connection.get_position(position_id)
                    # Si la position existe ou est en cour d'exécution 
                    if position is not None:
                        # Récupération du prix d'entré et take profit de la position 
                        opening_price = position['openPrice']
                        takeprofit = position['takeProfit']
                        # Appliquez un breakeven pour sur la position de la liste
                        await connection.modify_position(position_id, stop_loss=opening_price, take_profit=takeprofit)
                        update.effective_message.reply_text(f"Breakeven défini pour la position {position_id}.")


        return result

    except Exception as error:
        logger.error(f'Error: {error}')
        update.effective_message.reply_text(f"Failed to close trades. Error: {error}")


async def ConnectEditTrade(update: Update, context: CallbackContext, trade: dict, signalInfos_converted):
    """Edit Stop ongoing trades with spread consideration."""
    api = MetaApi(API_KEY)

    try:
        account = await api.metatrader_account_api.get_account(ACCOUNT_ID)
        initial_state = account.state
        deployed_states = ['DEPLOYING', 'DEPLOYED']

        if initial_state not in deployed_states:
            logger.info('Deploying account')
            await account.deploy()

        logger.info('Waiting for API server to connect to broker ...')
        await account.wait_connected()

        connection = account.get_rpc_connection()
        await connection.connect()
        logger.info('Waiting for SDK to synchronize to terminal state ...')
        await connection.wait_synchronized()

        if update.effective_message.reply_to_message is None:
            if 'BE' in update.effective_message.text:
                # Gérer la position spécifique pour un "BreakEven"
                position = await connection.get_position(trade['trade_id'])

                # Récupérer le spread pour ajuster le niveau de breakeven
                market_data = await connection.get_symbol_price(position['symbol'])
                spread = market_data['ask'] - market_data['bid']
                adjusted_stop_loss = (
                    position['openPrice'] + spread if position['type'] == 'POSITION_TYPE_BUY' else position['openPrice'] - spread
                )

                # Mettre à jour la position
                await connection.modify_position(
                    position['id'], stop_loss=adjusted_stop_loss, take_profit=position['takeProfit']
                )
                update.effective_message.reply_text(
                    f"BreakEven ajusté pour {position['id']} ({position['symbol']}) avec spread : {spread:.5f}."
                )
            else:
                # Gérer toutes les positions selon le cas spécifié
                positions = await connection.get_positions()

                for position in positions:
                    # Vérifier les critères de correspondance de `symbol` et `ordertype`
                    if (
                        (not trade['symbol'] and not trade['ordertype'])
                        or (position['symbol'] == trade['symbol'] and position['type'].endswith(trade['ordertype']))
                        or (not trade['symbol'] and position['type'].endswith(trade['ordertype']))
                        or (not trade['ordertype'] and position['symbol'] == trade['symbol'])
                    ):
                        market_data = await connection.get_symbol_price(position['symbol'])
                        spread = market_data['ask'] - market_data['bid']

                        if 'BRV' in update.effective_message.text:  # BreakEven
                            adjusted_stop_loss = (
                                position['openPrice'] + spread
                                if position['type'] == 'POSITION_TYPE_BUY'
                                else position['openPrice'] - spread
                            )
                            await connection.modify_position(
                                position['id'], stop_loss=adjusted_stop_loss, take_profit=position['takeProfit']
                            )
                            update.effective_message.reply_text(
                                f"BreakEven ajusté pour {position['id']} ({position['symbol']}) avec spread : {spread:.5f}."
                            )
                        elif 'SL' in update.effective_message.text and 'TP' in update.effective_message.text:
                            await connection.modify_position(
                                position['id'], stop_loss=trade['new_sl'], take_profit=trade['new_tp']
                            )
                            update.effective_message.reply_text(
                                f"StopLoss: {trade['new_sl']} & TakeProfit: {trade['new_tp']} définis pour {position['id']}."
                            )
                        elif 'SL' in update.effective_message.text:
                            await connection.modify_position(
                                position['id'], stop_loss=trade['newstop'], take_profit=position['takeProfit']
                            )
                            update.effective_message.reply_text(
                                f"StopLoss: {trade['newstop']} défini pour {position['id']}."
                            )
                        elif 'TP' in update.effective_message.text:
                            await connection.modify_position(
                                position['id'], stop_loss=position['stopLoss'], take_profit=trade['newstop']
                            )
                            update.effective_message.reply_text(
                                f"TakeProfit: {trade['newstop']} défini pour {position['id']}."
                            )
        else:
            messageid = update.effective_message.reply_to_message.message_id
            for position_id in signalInfos_converted[messageid]:
                position = await connection.get_position(position_id)
                if position is not None:
                    market_data = await connection.get_symbol_price(position['symbol'])
                    spread = market_data['ask'] - market_data['bid']

                    if 'BRV' in update.effective_message.text:  # BreakEven
                        adjusted_stop_loss = (
                            position['openPrice'] + spread
                            if position['type'] == 'POSITION_TYPE_BUY'
                            else position['openPrice'] - spread
                        )
                        await connection.modify_position(
                            position_id, stop_loss=adjusted_stop_loss, take_profit=position['takeProfit']
                        )
                        update.effective_message.reply_text(
                            f"BreakEven ajusté pour {position_id} ({position['symbol']}) avec spread : {spread:.5f}."
                        )
                    elif 'SL' in update.effective_message.text and 'TP' in update.effective_message.text:
                        await connection.modify_position(
                            position_id, stop_loss=trade['new_sl'], take_profit=trade['new_tp']
                        )
                        update.effective_message.reply_text(
                            f"StopLoss: {trade['new_sl']} & TakeProfit: {trade['new_tp']} définis pour {position_id}."
                        )
                    elif 'SL' in update.effective_message.text:
                        await connection.modify_position(
                            position_id, stop_loss=trade['newstop'], take_profit=position['takeProfit']
                        )
                        update.effective_message.reply_text(
                            f"StopLoss: {trade['newstop']} défini pour {position_id}."
                        )
                    elif 'TP' in update.effective_message.text:
                        await connection.modify_position(
                            position_id, stop_loss=position['stopLoss'], take_profit=trade['newstop']
                        )
                        update.effective_message.reply_text(
                            f"TakeProfit: {trade['newstop']} défini pour {position_id}."
                        )

    except Exception as error:
        logger.error(f'Error: {error}')
        update.effective_message.reply_text(f"Failed to set new Stop on the trades. Error: {error}")


async def ConnectPlaceTrade(update: Update, context: CallbackContext, trade: dict, enterTrade: bool):
    """Attempts connection to MetaAPI and MetaTrader to place trade.

    Arguments:
        update: update from Telegram
        trade: dictionary that stores trade information

    Returns:
        A coroutine that confirms that the connection to MetaAPI/MetaTrader and trade placement were successful
    """

    # creates connection to MetaAPI
    api = MetaApi(API_KEY)
    
    try:
        account = await api.metatrader_account_api.get_account(ACCOUNT_ID)
        initial_state = account.state
        deployed_states = ['DEPLOYING', 'DEPLOYED']

        if initial_state not in deployed_states:
            #  wait until account is deployed and connected to broker
            logger.info('Deploying account')
            await account.deploy()

        logger.info('Waiting for API server to connect to broker ...')
        await account.wait_connected()

        # connect to MetaApi API
        connection = account.get_rpc_connection()
        await connection.connect()

        # wait until terminal state synchronized to the local state
        logger.info('Waiting for SDK to synchronize to terminal state ...')
        await connection.wait_synchronized()

        # Récupérer la connexion à partir du contexte de l'application
        #connection = context.bot_data['mt_streaming_connection']
        #update.effective_message.reply_text(f"CONNECTION: {connection}")

        # obtains account information from MetaTrader server
        #account_information = connection.terminal_state.account_information
        account_information = await connection.get_account_information()

        # calculates the stop loss in pips
        if(trade['Symbol'] in CRYPTO):
            multiplier = 10

        elif(trade['Symbol'] in INDICES):
            multiplier = 1

        elif(trade['Symbol'] == 'XAUUSD' or trade['Symbol'] == 'XAUEUR' or trade['Symbol'] == 'XAUGBP' ):
            multiplier = 0.1

        elif(trade['Symbol'] == 'XAGUSD' or trade['Symbol'] == 'XAGEUR' or trade['Symbol'] == 'XAGGBP'):
            multiplier = 0.001

        elif('JPY' in trade['Symbol'] or str(trade['Entry']).index('.') >= 2 ):
            multiplier = 0.01

        else:
            multiplier = 0.0001


        # Symbols editing
        #if 'ACCOUNT_TRADE_MODE_DEMO' in account_information['type']:
        if 'Trial'.lower() in account_information['name'].lower() or 'STLR'.lower() in account_information['name'].lower():
            # Calculer la vrai balance du challenge
            balance = (account_information['balance'] * 6) / 100
        else:
            balance = account_information['balance']

        #if 'Competition' in account_information['name']:
            #if(trade['PositionSize'] > 3):
                #trade['PositionSize'] = 3
                #if(trade['PositionSize'] > 3):
                    #trade['PositionSize'] = 3
            #elif(trade['Symbol'] in FOREX):
                #trade['Symbol'] = trade['Symbol']+".i"
            #logger.info(trade['Symbol'])

        if 'Eightcap' in account_information['broker']:
            if(multiplier == 1):
                trade['Symbol'] = trade['Symbol']+".b"
            elif(trade['Symbol'] in FOREX):
                trade['Symbol'] = trade['Symbol']+".i"
            #logger.info(trade['Symbol'])

        elif 'exness' in account_information['broker'].lower():
            if 'Standard'.lower() in account_information['name'].lower():
                trade['Symbol'] = trade['Symbol']+"m"
                #logger.info(trade['Symbol'])
            elif 'ZeroSpread'.lower() in account_information['name'].lower():
                trade['Symbol'] = trade['Symbol']+"z"
                #logger.info(trade['Symbol'])
            #else:
                #trade['Symbol'] = trade['Symbol']
                #logger.info(trade['Symbol'])

        elif 'xm global' in account_information['broker'].lower():
            if trade['Symbol'] == 'XAUUSD':
                trade['Symbol'] = 'GOLD'
                #logger.info(trade['Symbol'])

        elif 'AXSE Brokerage' in account_information['broker']:
            trade['Symbol'] = trade['Symbol']+"_raw"
            #logger.info(trade['Symbol'])


        # checks if the order is a market execution to get the current price of symbol
        if('Limit' not in trade['OrderType'] or 'Stop' not in trade['OrderType'] or 'Limits' not in trade['OrderType']):
            #price = connection.terminal_state.price(symbol=trade['Symbol'])
            price = await connection.get_symbol_price(symbol=trade['Symbol'])

            # uses bid price if the order type is a buy
            if(trade['OrderType'] == 'Buy' or trade['OrderType'] == 'ACHAT'):
                trade['Entry'] = float(price['bid'])

            # uses ask price if the order type is a sell
            if(trade['OrderType'] == 'Sell' or trade['OrderType'] == 'VENTE'):
                trade['Entry'] = float(price['ask'])


        # produces a table with trade information
        GetTradeInformation(update, trade, balance, account_information['currency'], multiplier)


        # checks if the user has indicated to enter trade
        if(enterTrade == True):

            # enters trade on to MetaTrader account
            update.effective_message.reply_text("Entering trade on MetaTrader Account ... 👨🏾‍💻")

            tradeid = []

            try:
                # executes buy market execution order
                if(trade['OrderType'] == 'Buy' or trade['OrderType'] == 'ACHAT'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_market_buy_order(trade['Symbol'], round(trade['PositionSize'] / len(trade['TP']), 2), trade['StopLoss'], takeProfit)
                        tradeid.append(result['positionId'])

                # executes buy limit order
                elif(trade['OrderType'] == 'Buy Limit'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_limit_buy_order(trade['Symbol'], round(trade['PositionSize'] / len(trade['TP']), 2), trade['Entry'], trade['StopLoss'], takeProfit)
                        tradeid.append(result['orderId'])

                # executes buy Limits order
                elif(trade['OrderType'] == 'Buy Limits'):
                    for i in range(len(trade['Entry'])):
                        result = await connection.create_limit_buy_order(trade['Symbol'], trade['PositionSize'][i], trade['Entry'][i], trade['StopLoss'], trade['TP'][i])
                        tradeid.append(result['orderId'])

                # executes buy stop order
                elif(trade['OrderType'] == 'Buy Stop'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_stop_buy_order(trade['Symbol'], round(trade['PositionSize'] / len(trade['TP']), 2), trade['Entry'], trade['StopLoss'], takeProfit)
                        tradeid.append(result['orderId'])

                # executes sell market execution order
                elif(trade['OrderType'] == 'Sell' or trade['OrderType'] == 'VENTE'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_market_sell_order(trade['Symbol'], round(trade['PositionSize'] / len(trade['TP']), 2), trade['StopLoss'], takeProfit)
                        tradeid.append(result['positionId'])

                # executes sell limit order
                elif(trade['OrderType'] == 'Sell Limit'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_limit_sell_order(trade['Symbol'], round(trade['PositionSize'] / len(trade['TP']), 2), trade['Entry'], trade['StopLoss'], takeProfit)
                        tradeid.append(result['orderId'])

                # executes sell Limits order
                elif(trade['OrderType'] == 'Sell Limits'):
                    for i in range(len(trade['Entry'])):
                        result = await connection.create_limit_sell_order(trade['Symbol'], trade['PositionSize'][i], trade['Entry'][i], trade['StopLoss'], trade['TP'][i])
                        tradeid.append(result['orderId'])

                # executes sell stop order
                elif(trade['OrderType'] == 'Sell Stop'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_stop_sell_order(trade['Symbol'], round(trade['PositionSize'] / len(trade['TP']), 2), trade['Entry'], trade['StopLoss'], takeProfit)
                        tradeid.append(result['orderId'])

                # prints PositionID to user
                update.effective_message.reply_text(tradeid)

                # sends success message to user
                update.effective_message.reply_text("Trade entered successfully! 💰")
                
                # prints success message to console
                logger.info('\nTrade entered successfully!')
                logger.info('Result Code: {}\n'.format(result['stringCode']))
            
            except Exception as error:
                logger.info(f"\nTrade failed with error: {error}\n")
                update.effective_message.reply_text(f"There was an issue 😕\n\nError Message:\n{error}")
    
    except Exception as error:
        logger.error(f'Error: {error}')
        update.effective_message.reply_text(f"There was an issue with the connection 😕\n\nError Message:\n{error}")
    
    return tradeid


async def ConnectGetOngoingTrades(update: Update, context: CallbackContext) -> None:
    """Retrieves information about all ongoing trades and account details.

    Arguments:
        update: update from Telegram
    """
    api = MetaApi(API_KEY)

    try:
        account = await api.metatrader_account_api.get_account(ACCOUNT_ID)
        initial_state = account.state
        deployed_states = ['DEPLOYING', 'DEPLOYED']

        if initial_state not in deployed_states:
            # Wait until account is deployed and connected to broker
            logger.info('Deploying account')
            await account.deploy()

        logger.info('Waiting for API server to connect to broker ...')
        await account.wait_connected()

        # Connect to MetaApi API
        connection = account.get_rpc_connection()
        await connection.connect()

        # Wait until terminal state synchronized to the local state
        logger.info('Waiting for SDK to synchronize to terminal state ...')
        await connection.wait_synchronized()

        # Fetch account details: equity, balance and currency
        account_info = await connection.get_account_information()
        equity = account_info['equity']
        balance = account_info['balance']
        currency = account_info['currency']


        # Fetch open positions
        positions = await connection.get_positions()

        if not positions:
            update.effective_message.reply_text(
                f"No ongoing trades at the moment.\n\n"
                f"Account Balance: <b>{balance:.2f} {currency}</b>\n",
                parse_mode=ParseMode.HTML
            )
            return

        total_profit = 0  # Variable to keep track of total profit/loss

        for position in positions:
            # Add profit/loss of the current position to the total
            total_profit += position['profit']

            # Format entry time
            entry_time = position['time'].strftime('%d-%m-%Y %H:%M:%S')

            # Display individual trade information
            trade_info = f"{position['type']}\n" \
                         f"Symbol: {position['symbol']}\n" \
                         f"Volume: {position['volume']}\n" \
                         f"Profit: {position['profit']:.2f} {currency}\n" \
                         f"ORDER ID: {position['id']}\n" \
                         f"Entry Time: {entry_time}\n"

            update.effective_message.reply_text(f'<pre>{trade_info}</pre>', parse_mode=ParseMode.HTML)

        # Send total profit/loss after listing all trades
        total_profit_message = f"Total Profit/Loss (P/L): {total_profit:.2f} {currency}"
        update.effective_message.reply_text(f'<b>{total_profit_message}</b>', parse_mode=ParseMode.HTML)

        # Send account info after listing total profit/loss and all trades
        summary_message = (
            f"<b>Account Summary</b>\n"
            f"Balance: <b>{balance:.2f} {currency}</b>\n"
            f"Equity: <b>{equity:.2f} {currency}</b>\n"
        )
        update.effective_message.reply_text(summary_message, parse_mode=ParseMode.HTML)

    except Exception as error:
        logger.error(f'Error: {error}')
        update.effective_message.reply_text(f"Failed to retrieve ongoing trades. Error: {error}")

    return


async def ConnectGetTradeHistory(update: Update, context: CallbackContext) -> None:
    """Retrieves trade history and updates an Excel file.
    
    Arguments:
        update: update from Telegram
    """
    api = MetaApi(API_KEY)

    try:
        # account = await api.metatrader_account_api.get_account(ACCOUNT_ID)
        # initial_state = account.state
        # deployed_states = ['DEPLOYING', 'DEPLOYED']

        # if initial_state not in deployed_states:
        #     # Wait until account is deployed and connected to broker
        #     logger.info('Deploying account')
        #     await account.deploy()

        # logger.info('Waiting for API server to connect to broker ...')
        # await account.wait_connected()

        # # Connect to MetaApi API
        # connection = account.get_rpc_connection()
        # await connection.connect()

        # # Wait until terminal state synchronized to the local state
        # logger.info('Waiting for SDK to synchronize to terminal state ...')
        # await connection.wait_synchronized()

        # Fetch historical trades
        #deals_response = await connection.get_deals_by_time_range(datetime.now() - timedelta(days=30), datetime.now())

        #historyOrders = await connection.get_history_orders_by_time_range(datetime.now() - timedelta(days=30), datetime.now())
        history = [{"id":"89917163","platform":"mt5","type":"ORDER_TYPE_BUY_LIMIT","state":"ORDER_STATE_FILLED","symbol":"GBPJPY","magic":0,"time":"2024-06-12T16:43:08.835Z","brokerTime":"2024-06-12 16:43:08.835","openPrice":200.072,"volume":0.16,"currentVolume":0,"positionId":"89917163","doneTime":"2024-06-12T17:31:11.430Z","doneBrokerTime":"2024-06-12 17:31:11.430","reason":"ORDER_REASON_EXPERT","fillingMode":"ORDER_FILLING_RETURN","expirationType":"ORDER_TIME_GTC","stopLoss":199.931,"takeProfit":200.581,"accountCurrencyExchangeRate":1},{"id":"90661456","platform":"mt5","type":"ORDER_TYPE_BUY_LIMIT","state":"ORDER_STATE_FILLED","symbol":"BTCUSD","magic":0,"time":"2024-06-14T19:07:13.833Z","brokerTime":"2024-06-14 19:07:13.833","openPrice":65310.86,"volume":0.04,"currentVolume":0,"positionId":"90661456","doneTime":"2024-06-14T19:14:56.329Z","doneBrokerTime":"2024-06-14 19:14:56.329","reason":"ORDER_REASON_EXPERT","fillingMode":"ORDER_FILLING_RETURN","expirationType":"ORDER_TIME_GTC","stopLoss":65028.96,"takeProfit":66750.99,"accountCurrencyExchangeRate":1},{"id":"90679330","platform":"mt5","type":"ORDER_TYPE_SELL","state":"ORDER_STATE_FILLED","symbol":"BTCUSD","magic":0,"time":"2024-06-14T21:36:13.742Z","brokerTime":"2024-06-14 21:36:13.742","openPrice":66315.6,"volume":0.04,"currentVolume":0,"positionId":"90661455","doneTime":"2024-06-14T21:36:13.744Z","doneBrokerTime":"2024-06-14 21:36:13.744","reason":"ORDER_REASON_TP","fillingMode":"ORDER_FILLING_IOC","expirationType":"ORDER_TIME_GTC","brokerComment":"[tp 66315.60]","accountCurrencyExchangeRate":1}]
        logger.info(history)

        # Update Excel file with the retrieved data
        update_excel_file(history)

        # Send the updated Excel file via Telegram
        send_excel_file(update, context)

    except Exception as error:
        logger.error(f'Error: {error}')
        update.effective_message.reply_text(f"Failed to retrieve trade history. Error: {error}")

    return


# Handler Functions
def PlaceTrade(update: Update, context: CallbackContext) -> int:
    """Parses trade and places on MetaTrader account.   
    
    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks
    """
    
    # checks if the trade has already been parsed or not
    #if(context.chat_data['trade'] == None):
    try:
        if update.effective_message.caption is not None:
            text_received = update.effective_message.caption.replace('  ', ' ')
        else:
            text_received = update.effective_message.text.replace('  ', ' ')
        #chat_title = update.message.forward_from_chat.title
              
        # parses signal from Telegram message
        trade = ParseSignal(text_received)
        
        # checks if there was an issue with parsing the trade
        if(not(trade)):
            raise Exception('Invalid Trade')
        
        # sets the user context trade equal to the parsed trade and extract signal 
        context.chat_data['trade'] = trade

        update.effective_message.reply_text("Trade Successfully Parsed! 🥳\nConnecting to MetaTrader ... \n(May take a while) ⏰")
        logger.info(trade)

    except Exception as error:
        logger.error(f'Error: {error}')
        errorMessage = f"There was an error parsing this trade 😕\n\nError: {error}\n\n\nOr use the /cancel to command to cancel this action."
        update.effective_message.reply_text(errorMessage)

        # returns to TRADE state to reattempt trade parsing
        return TRADE
    
    signalInfos = read_data_from_json()
    
    # extraction of the signal messageID's 
    if update.effective_message.message_id not in signalInfos:
        signalInfos[update.effective_message.message_id] = []

    # attempts connection to MetaTrader and places trade
    tradeid = asyncio.run(ConnectPlaceTrade(update, context, context.chat_data['trade'], True))
    #tradeid = ["409804691", "409804692", "409804693"]

    # adding tradeid values in signalInfos
    signalInfos[update.effective_message.message_id].extend(tradeid)
    #signalInfos.update(signalInfos[update.effective_message.message_id].extend(tradeid))
    #update.effective_message.reply_text(signalInfos)

    write_data_to_json(signalInfos)
    
    # removes trade from user context data
    context.chat_data['trade'] = None

    return ConversationHandler.END

def CalculateTrade(update: Update, context: CallbackContext) -> int:
    """Parses trade and places on MetaTrader account.   
    
    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks
    """

    # checks if the trade has already been parsed or not
    #if(context.chat_data['trade'] == None):

    try: 
        # parses signal from Telegram message
        trade = ParseSignal(update.effective_message.text)
        
        # checks if there was an issue with parsing the trade
        if(not(trade)):
            raise Exception('Invalid Trade')

        # sets the user context trade equal to the parsed trade
        context.chat_data['trade'] = trade
        update.effective_message.reply_text("Trade Successfully Parsed! 🥳\nConnecting to MetaTrader ... (May take a while) ⏰")
    
    except Exception as error:
        logger.error(f'Error: {error}')
        errorMessage = f"There was an error parsing this trade 😕\n\nError: {error}\n\nPlease re-enter trade with this format:\n\nBUY/SELL SYMBOL \nTP \nSL \n\nOr use the /cancel to command to cancel this action."
        update.effective_message.reply_text(errorMessage)

        # returns to CALCULATE to reattempt trade parsing
        return CALCULATE
    
    # attempts connection to MetaTrader and calculates trade information
    asyncio.run(ConnectPlaceTrade(update, context.chat_data['trade'], False))

    # asks if user if they would like to enter or decline trade
    update.effective_message.reply_text("Would you like to enter this trade?\nTo enter, select: /yes\nTo decline, select: /no")

    return DECISION

def unknown_command(update: Update, context: CallbackContext) -> None:
    """Checks if the user is authorized to use this bot or shares to use /help command for instructions.

    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks
    """
    if(not(update.effective_message.chat.username == TELEGRAM_USER)):
        update.effective_message.reply_text("You are not authorized to use this bot! 🙅🏽‍♂️")
        return

    update.effective_message.reply_text("Unknown command. Use /trade to place a trade or /calculate to find information for a trade. You can also use the /help command to view instructions for this bot.")

    return

def TakeProfitTrade(update: Update, context: CallbackContext) -> int:
    """Starts process of parsing TP signal and closing trade on MetaTrader account.

    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks

    """

    # checks if the trade has already been parsed or not
    #if(context.chat_data['trade'] == None):

    messageid = update.effective_message.reply_to_message.message_id
    signalInfos = read_data_from_json()
    trade_id = 0
    trade = {}

    # Convertir les valeurs de type chaîne en entiers
    signalInfos_converted = {int(key): value for key, value in signalInfos.items()}
    #update.effective_message.reply_text(signalInfos_converted)

    # Sérialisation des clés "key"
    cles_serializables = list(signalInfos_converted.keys())

    try: 

        # parses signal from Telegram message and determines the trade to close 
        if('TP1'.lower() in update.effective_message.text.lower() or 'SECURE'.lower() in update.effective_message.text.lower() or 'move'.lower() in update.effective_message.text.lower() and messageid in cles_serializables):
            trade_id = signalInfos_converted[messageid][0]
            
        elif('TP2'.lower() in update.effective_message.text.lower() and messageid in cles_serializables):
            trade_id = signalInfos_converted[messageid][1]

        elif('Fermez'.lower() in update.effective_message.text.lower() and messageid in cles_serializables):
            trade_id = signalInfos_converted[messageid][2]


        # Fermez la position de la liste
        resultclose = asyncio.run(ConnectCloseTrade(update, context, trade, trade_id, signalInfos_converted))
        
        # checks if there was an issue with parsing the trade
        #if(not(signalInfos)):
        #    raise Exception('Invalid Close Signal')

    
    except Exception as error:
        logger.error(f'Error: {error}')
        errorMessage = f"There was an error parsing this signal 😕\n\nError: {error}\n\n"
        update.effective_message.reply_text(errorMessage)

        # returns to TRADE state to reattempt trade parsing
        return TRADE
    

    # removes trade from user context data
    context.chat_data['trade'] = None

    return ConversationHandler.END

def EditStopTrade(update: Update, context: CallbackContext) -> int:
    """Starts process of parsing TP signal and closing trade on MetaTrader account.

    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks

    """

    # checks if the trade has already been parsed or not
    #if(context.chat_data['trade'] == None):

    #messageid = update.effective_message.reply_to_message.message_id
    signalInfos = read_data_from_json()
    #trade_id = 0

    # Convertir les valeurs de type chaîne en entiers
    signalInfos_converted = {int(key): value for key, value in signalInfos.items()}

    # Sérialisation des clés "key"
    #cles_serializables = list(signalInfos_converted.keys())

    try: 

        """""
        # parses signal from Telegram message and determines the trade to edit 
        if messageid is None:
            trade_id = signalInfos_converted[messageid][0]
            
        else:
            trade_id = signalInfos_converted[messageid][1]
        """
        
        # parses signal from Telegram message
        trade = ParseSignal(update.effective_message.text)
        
        # checks if there was an issue with parsing the trade
        if(not(trade)):
            raise Exception('Invalid Trade')

        # sets the user context trade equal to the parsed trade and extract messageID 
        context.chat_data['trade'] = trade
        update.effective_message.reply_text("Signal Successfully Parsed! 🥳\nConnecting to MetaTrader ... \n(May take a while) ⏰")
        logger.info(trade)

        # checks if there was an issue with parsing the trade
        #if(not(signalInfos)):
        #    raise Exception('Invalid Close Signal')

    
    except Exception as error:
        logger.error(f'Error: {error}')
        errorMessage = f"There was an error parsing this signal 😕\n\nError: {error}\n\n"
        update.effective_message.reply_text(errorMessage)

        # returns to TRADE state to reattempt trade parsing
        return TRADE
    
    
    # if trade['trade_id'] is not None: 
    #     trade_id = trade['trade_id']
    #     #update.effective_message.reply_text(trade_id)
    
    # Modifiez le stoploss des positions de la liste
    resultedit = asyncio.run(ConnectEditTrade(update, context, trade, signalInfos_converted))
 
    # removes trade from user context data
    context.chat_data['trade'] = None

    return ConversationHandler.END

def CloseAllTrade(update: Update, context: CallbackContext) -> int:
    """Starts process of parsing Closing signal and closing trade on MetaTrader account.

    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks

    """

    # checks if the trade has already been parsed or not
    #if(context.chat_data['trade'] == None):

    #messageid = update.effective_message.reply_to_message.message_id
    signalInfos = read_data_from_json()
    trade_id = 0


    # Convertir les valeurs de type chaîne en entiers
    signalInfos_converted = {int(key): value for key, value in signalInfos.items()}

    # Sérialisation des clés "key"
    #cles_serializables = list(signalInfos_converted.keys())

    try: 
       
        # parses signal from Telegram message
        trade = ParseSignal(update.effective_message.text)
        
        # checks if there was an issue with parsing the trade
        if(not(trade)):
            raise Exception('Invalid close signal')
        
        # sets the user context trade equal to the parsed trade and extract messageID 
        context.chat_data['trade'] = trade

        # checks if trade['trade_id'] exist
        if trade['trade_id']: 
            trade_id = trade['trade_id']
            #update.effective_message.reply_text(trade_id)
        
        update.effective_message.reply_text("Signal Successfully Parsed! 🥳\nConnecting to MetaTrader ... \n(May take a while) ⏰")
        logger.info(trade)

    
    except Exception as error:
        logger.error(f'Error: {error}')
        errorMessage = f"There was an error parsing this signal 😕\n\nError: {error}\n\n"
        update.effective_message.reply_text(errorMessage)

        # returns to TRADE state to reattempt trade parsing
        return TRADE
    
    
    # Fermerture des positions de la liste
    resultclose = asyncio.run(ConnectCloseTrade(update, context, trade, trade_id, signalInfos_converted))
 
    # removes trade from user context data
    context.chat_data['trade'] = None

    return ConversationHandler.END

def get_exchange_rate():
    global exchange_rate
    # Vérifier si le taux de change a déjà été récupéré
    if exchange_rate is None:
        # Appel à une API de taux de change
        response = requests.get("https://api.exchangerate-api.com/v4/latest/USD")
        data = response.json()
        # Récupération du taux de change USD/XOF
        exchange_rate = data['rates']['XOF']
    return exchange_rate

def xof_to_usd(amount_xof):
    # Obtenir le taux de change
    exchange_rate = get_exchange_rate()
    amount_usd = amount_xof / exchange_rate
    return amount_usd

# Fonction pour gérer les messages
def handle_message(update: Update, context: CallbackContext):
    if update.effective_message.caption is not None:
        text_received = update.effective_message.caption
    else:
        text_received = update.effective_message.text
    #chat_title = update.message.forward_from_chat.title
    #logger.info(text_received)

    # converts message to list of strings for parsing
    signal = text_received.splitlines()
    #logger.info(len(signal))

    # Liste des expressions régulières et fonctions associées
    if (len(signal) < 3):
        regex_functions = {
                r"\bPRENEZ LE\b": TakeProfitTrade, # message handler for Take Profit
                r"\bTOUCHÉ\b": TakeProfitTrade, # message handler for Take Profit
                r"\bMETTRE LE\b": EditStopTrade, # message handler to edit SL

                r"\bSL\b": EditStopTrade, # message handler to edit SL
                r"\bTP\b": EditStopTrade, # message handler to edit TP
                
                r"\bBRV\b": EditStopTrade, # message handler to BREAKEVEN Position By ORDERTYPE OR SYMBOL 
                r"\bBE\b": EditStopTrade, # message handler to BREAKEVEN Position By ID
                
                r"\bPARTIELS\b": CloseAllTrade, # message handler to CLOSE POSITION PARTIALY By ORDERTYPE , SYMBOL
                r"\bPARTIEL\b": CloseAllTrade, # message handler to CLOSE POSITION PARTIALY By ID
                r"\bCLORES\b": CloseAllTrade, # message handler to CLOSE POSITION By ORDERTYPE , SYMBOL
                r"\bCLORE\b": CloseAllTrade, # message handler to CLOSE POSITION By ID

        }
    else:
        # if (len(signal) == 7):
        #     regex_functions = {
        #             r"\bOuvert\b": PlaceTrade, # message handler for entering trade
        #             #r"\bFermez le trade\b": TakeProfitTrade, # message handler for Take Profit the last one        

        #             #r"\bRISK\b": PlaceTrade, # message handler for manualy enter trade

        #     }
        # else:
            regex_functions = {
                    r"\bBTCUSD\b": PlaceTrade, # message handler for entering trade
                    r"\bFermez le trade\b": TakeProfitTrade, # message handler for Take Profit the last one        

                    r"\bRISK\b": PlaceTrade, # message handler for manualy enter trade

                    r"\bSELL\b": PlaceTrade, # message handler for entering trade
                    r"\bBUY\b": PlaceTrade, # message handler for entering trade
                    r"\bSl\b": PlaceTrade, # message handler for entering trade
                    r"\bSL\b": PlaceTrade, # message handler for entering trade
                    r"\bsl\b": PlaceTrade, # message handler for entering trade
                    r"\bsL\b": PlaceTrade, # message handler for entering trade
                    #r"\btp2\b": PlaceTrade, # message handler for entering trade
                    #r"\btp 2\b": PlaceTrade, # message handler for entering trade
                    #r"\bTp2\b": PlaceTrade, # message handler for entering trade
                    #r"\bTp 2\b": PlaceTrade, # message handler for entering trade
                    #r"\bSL@\b": PlaceTrade, # message handler for entering trade
                    #r"\b💵TP:\b": PlaceTrade, # message handler for entering trade
                    #r"\b❌SL:\b": PlaceTrade, # message handler for entering trade
                    # r"\bEnter Slowly-Layer\b": PlaceTrade, # message handler for entering trade
                    
                    #r"\bclose half\b": CloseAllTrade, # message handler to CLOSE PARTIAL POSITION

            }


    """     if ('ELITE CLUB VIP'.lower() in chat_title.lower()):
            # Liste des expressions régulières et fonctions associées
            regex_functions = {
                r"\bTP\b": PlaceTrade, # message handler for entering trade
                r"\bSECURE PARTIALS MOVE\b": TakeProfitTrade, # message handler to Take Profit
                #r"\bFermez le trade\b": TakeProfitTrade, # message handler to Take Profit the last one
                #r"\bMETTRE LE SL\b": EditSlTrade, # message handler for edit SL
                # Ajoutez d'autres regex et fonctions associées ici
            }
            
        update.effective_message.reply_text(update.message.forward_from_chat.title)
    """
    # Vérifiez chaque regex pour trouver une correspondance dans le message
    for regex_pattern, func in regex_functions.items():
        if re.search(regex_pattern, text_received):
            func(update, context)
            break  # Sort de la boucle après avoir déclenché la première fonction trouvée

# Fonction pour lire les données du fichier JSON
def read_data_from_json():
    try:
        with open('data.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

# Fonction pour écrire les données dans le fichier JSON
def write_data_to_json(data):
    with open('data.json', 'w') as file:
        json.dump(data, file)

def update_excel_file(history):
    """Updates an Excel file with the retrieved trade history data.
    
    Arguments:
        history: list of historical trade data
    """
    file_path = 'Trading-journal-template.xlsx'
    wb = load_workbook(file_path)
    ws = wb['Trades']

    for trade in history:
        if isinstance(trade, dict):
            trade_info = [
                trade.get('id', 'N/A'),
                datetime.strptime(trade.get('time', 'N/A'), '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%d') if trade.get('time') else 'N/A',  # entryDate
                datetime.strptime(trade.get('doneTime', 'N/A'), '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%d') if trade.get('doneTime') else 'N/A',  # exitDate
                trade.get('type', 'N/A'),
                trade.get('symbol', 'N/A'),
                trade.get('openPrice', 'N/A'),  # entryPrice
                trade.get('closePrice', 'N/A'),  # exitPrice (if available, otherwise N/A)
                trade.get('profit', 'N/A'),
                trade.get('volume', 'N/A'),
                'N/A',  # fees (if available, otherwise N/A)
                'N/A',  # gainPercent (if available, otherwise N/A)
                'N/A',  # win (if available, otherwise N/A)
                'N/A',  # tradeCount (if available, otherwise N/A)
                datetime.strptime(trade.get('time', 'N/A'), '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%d %H:%M:%S') if trade.get('time') else 'N/A',  # entryDateTime
                datetime.strptime(trade.get('doneTime', 'N/A'), '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%d %H:%M:%S') if trade.get('doneTime') else 'N/A',  # exitDateTime
                'N/A'   # accProfit (if available, otherwise N/A)
            ]
            ws.append(trade_info)
        else:
            logger.warning(f"Invalid trade format: {trade}")

    # Save the workbook
    wb.save(file_path)
    logger.info(f"Trade history has been updated in '{file_path}'.")

def send_excel_file(update: Update, context: CallbackContext):
    """Sends the updated Excel file via Telegram.
    
    Arguments:
        update: update from Telegram
        context: callback context from Telegram
    """
    chat_id = update.message.chat_id
    context.bot.send_document(chat_id, document=open('Trading-journal-template.xlsx', 'rb'))


# Fonction pour envoyer un message
""" def send_periodic_message(update):
    chat_id = update.effective_message.chat_id
    message_text = 'Message à envoyer toutes les 5 minutes'
    update.effective_message.reply_text(message_text)
 """
# Handler pour déclencher l'envoi périodique de message
""" def periodic_handler(update, context):
    while True:
        # Envoi du message périodique
        for update in context.bot.updates:
            send_periodic_message(update)
        asyncio.sleep(300)  # Attendre 5 minutes avant d'envoyer le prochain message
 """


# Command Handlers
def welcome(update: Update, context: CallbackContext) -> None:
    """Sends welcome message to user.

    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks
    """

    welcome_message = "Welcome to the FX Signal Copier Telegram Bot! 💻💸\n\nYou can use this bot to enter trades directly from Telegram and get a detailed look at your risk to reward ratio with profit, loss, and calculated lot size. You are able to change specific settings such as allowed symbols, risk factor, and more from your personalized Python script and environment variables.\n\nUse the /help command to view instructions and example trades."
    
    # sends messages to user
    update.effective_message.reply_text(welcome_message)

    return

def help(update: Update, context: CallbackContext) -> None:
    """Sends a help message when the command /help is issued

    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks
    """

    help_message = "This bot is used to automatically enter trades onto your MetaTrader account directly from Telegram. To begin, ensure that you are authorized to use this bot by adjusting your Python script or environment variables.\n\nThis bot supports all trade order types (Market Execution, Limit, and Stop)\n\nAfter an extended period away from the bot, please be sure to re-enter the start command to restart the connection to your MetaTrader account."
    commands = "List of Bot commands:\n/start : displays welcome message\n/help : displays list of commands and example trades\n/trade : takes in user inputted trade for parsing and placement\n/calculate : calculates trade information for a user inputted trade\n/ongoing_trades : Retrieves information about all ongoing trades.\n"
    trade_command = "List of Trades Commands 💴:" "\n\n\SL\ # message handler to edit SL\nEx: SL 10000 BUY BTCUSD, " "\n\n\TP\ # message handler to edit TP\nEx: TP 20000 BUY BTCUSD" "\n\n\BRV\ # message handler to BREAKEVEN Position By ORDERTYPE OR SYMBOL\nEx: BRV BUY, BRV BTCUSD, BRV BUY BTCUSD" "\n\n\BE\ # message handler to BREAKEVEN Position By ID\nEx: BE 2738574" "\n\n\PARTIELS\ # message handler to CLOSE POSITION PARTIALY % By ORDERTYPE , SYMBOL\nEx: PARTIELS 30 BUY, PARTIELS 30 BTCUSD, PARTIELS 30 BUY BTCUSD" "\n\n\PARTIEL\ # message handler to CLOSE POSITION PARTIALY % By ID\nEx: PARTIEL 30 2738574" "\n\n\CLORES\ # message handler to CLOSE POSITION By ORDERTYPE , SYMBOL \nEx: CLORES BUY, CLORES BTCUSD, CLORES BUY BTCUSD" "\n\n\CLORE\ # message handler to CLOSE POSITION By ID\nEx: CLORE 2738574"
    trade_example = "Example Trades 💴:\n\n"
    market_execution_example = "Market Execution:\n\nXAUUSD BUY 2776\nTP @ 2779.60\nTP @ 2783.20\nTP @ 2785.50\n\nSL @ 2773.60\nRISK 0.1\n\n"
    limit_example = "\nLimit Execution:\n\nSell Gold @2754-2756\n\nSl :2758\n\nTp1 :2750\nTp2 :2748\n\nRISK 0.1\n\nEnter Slowly-Layer with proper money management\n\nDo not rush your entries\n\n"
    note = "\nYou are able to enter up to two take profits. If two are entered, both trades will use half of the position size, and one will use TP1 while the other uses TP2.\n\nNote: Use 'NOW' as the entry to enter a market execution trade."

    # sends messages to user
    update.effective_message.reply_text(help_message)
    update.effective_message.reply_text(commands)
    update.effective_message.reply_text(trade_command)
    update.effective_message.reply_text(trade_example + market_execution_example + limit_example + note)

    return

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels and ends the conversation.   
    
    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks
    """

    update.effective_message.reply_text("Command has been canceled.")

    # removes trade from user context data
    context.chat_data['trade'] = None

    return ConversationHandler.END

def error(update: Update, context: CallbackContext) -> None:
    """Logs Errors caused by updates.

    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks
    """

    logger.warning('Update "%s" caused error "%s"', update, context.error)

    return

def Trade_Command(update: Update, context: CallbackContext) -> int:
    """Asks user to enter the trade they would like to place.

    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks
    """
    if(not(update.effective_message.chat.username == TELEGRAM_USER)):
        update.effective_message.reply_text("You are not authorized to use this bot! 🙅🏽‍♂️")
        return ConversationHandler.END
    
    # initializes the user's trade as empty prior to input and parsing
    context.chat_data['trade'] = None
    
    # asks user to enter the trade
    update.effective_message.reply_text("Please enter the trade that you would like to place.")

    return TRADE

def Calculation_Command(update: Update, context: CallbackContext) -> int:
    """Asks user to enter the trade they would like to calculate trade information for.

    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks
    """
    if(not(update.effective_message.chat.username == TELEGRAM_USER)):
        update.effective_message.reply_text("You are not authorized to use this bot! 🙅🏽‍♂️")
        return ConversationHandler.END

    # initializes the user's trade as empty prior to input and parsing
    context.chat_data['trade'] = None

    # asks user to enter the trade
    update.effective_message.reply_text("Please enter the trade that you would like to calculate.")

    return CALCULATE

def GetOpenTradeIDs(update: Update, context: CallbackContext):
    """Retrieves information about all ongoing trades.

    Arguments:
        update: update from Telegram
    """

    # attempts connection to MetaTrader and retreive ongoing trade
    asyncio.run(ConnectGetOngoingTrades(update, context))

    return

def GetMessageTradeIDs(update: Update, context: CallbackContext):
    """Retrieves information about all trades's ID with their message ID .

    """
    # Retrieves all trades's ID with their message ID from son file.
    signalInfos = read_data_from_json()

    update.effective_message.reply_text(signalInfos)

def GetTradeHistory(update: Update, context: CallbackContext):
    """Retrieves information about all ongoing trades.

    Arguments:
        update: update from Telegram
    """

    # attempts connection to MetaTrader and retreive ongoing trade
    asyncio.run(ConnectGetTradeHistory(update, context))

    return


# Initialise MetaApi
async def init_meta_api():
    meta_api = MetaApi(API_KEY)
    account = await meta_api.metatrader_account_api.get_account(ACCOUNT_ID)
    await account.wait_connected()
    return account.get_streaming_connection()


#async def main():
    streaming_connection = await init_meta_api()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    async def handle_new_position(event):
        position = event['position']
        # Gérer la nouvelle position reçue
        print('Nouvelle position:', position)

    # Ajouter des gestionnaires d'événements pour les différents événements de streaming
    streaming_connection.subscribe_positions('position', handle_new_position)

    # Lancer l'écoute des événements de streaming
    await streaming_connection.wait_ready()

    # Fonction de démarrage de votre bot
    async def start(update, context):
        await update.message.reply_text('Bot démarré avec succès!')

    dp.add_handler(CommandHandler("start", start))

    # Lancer le bot
    await updater.start_polling()

    # Maintenir le bot actif
    await updater.idle()

def main() -> None:
# async def main() -> None:
    """Runs the Telegram bot."""
    # Configuration du bot Telegram
    updater = Updater(TOKEN, use_context=True)

    # get the dispatcher to register handlers
    dp = updater.dispatcher

    # # Connect to Metatrader
    # api = MetaApi(API_KEY)

    # account = await api.metatrader_account_api.get_account(ACCOUNT_ID)
    # initial_state = account.state
    # deployed_states = ['DEPLOYING', 'DEPLOYED']

    # if initial_state not in deployed_states:
    #     #  wait until account is deployed and connected to broker
    #     logger.info('Deploying account')
    #     await account.deploy()

    # logger.info('Waiting for API server to connect to broker ...')
    # await account.wait_connected()

    # # connect to MetaApi API
    # connection = account.get_streaming_connection()
    # await connection.connect()
    
    # # access local copy of terminal state
    # terminalState = connection.terminal_state

    # # Stockage de la connexion dans le contexte de l'application
    # dp.bot_data['mt_streaming_connection'] = connection

    # # wait until terminal state synchronized to the local state
    # logger.info('Waiting for SDK to synchronize to terminal state ...')
    # await connection.wait_synchronized()

    # print(terminalState.connected)
    # print(terminalState.connected_to_broker)
    # print(terminalState.account_information)

    #logger.error(f'Error: {error}')
    #update.effective_message.reply_text(f"Failed to conneect to MetaTrader. Error: {error}")
    
    # message handler
    dp.add_handler(CommandHandler("start", welcome))

    # help command handler
    dp.add_handler(CommandHandler("help", help))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("trade", Trade_Command), CommandHandler("calculate", Calculation_Command)],
        states={
            TRADE: [MessageHandler(Filters.text & ~Filters.command, PlaceTrade)],
            CALCULATE: [MessageHandler(Filters.text & ~Filters.command, CalculateTrade)],
            DECISION: [CommandHandler("yes", PlaceTrade), CommandHandler("no", cancel)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # command to receive information about all ongoing trades.
    dp.add_handler(CommandHandler("ongoing_trades", GetOpenTradeIDs))

    # command to receive information about all trades and their message ID.
    dp.add_handler(CommandHandler("messagetrade_ids", GetMessageTradeIDs))

    # command to retreive all trades to an excel file.
    dp.add_handler(CommandHandler("trade_history", GetTradeHistory))  # New handler for trade history


    # conversation handler for entering trade or calculating trade information
    dp.add_handler(conv_handler)

    # Ajout du gestionnaire de message
    #dp.add_handler(CommandHandler("periodichandler", periodic_handler))

    # message handler for all messages that are not included in conversation handler
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command | Filters.chat_type.channel & ~Filters.command, handle_message))

    #dp.add_handler(MessageHandler(Filters.text & ~Filters.command, periodic_handler))


    # log all errors
    dp.add_error_handler(error)
    
    # listens for incoming updates from Telegram
    updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=APP_URL + TOKEN)
    updater.idle()

    return


if __name__ == '__main__':
    main()

    # Exécuter la boucle principale
    #asyncio.run(main())
