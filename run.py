#!/usr/bin/env python3
import asyncio
import logging
import math
import os
import re
import json
import requests

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

from datetime import datetime

from metaapi_cloud_sdk import MetaApi
from prettytable import PrettyTable
from telegram import ParseMode, Update
from telegram.ext import CommandHandler, Filters, MessageHandler, Updater, ConversationHandler, CallbackContext

# MetaAPI Credentials
API_KEY = os.environ.get("API_KEY")
ACCOUNT_ID = os.environ.get("ACCOUNT_ID")

# Telegram Credentials
TOKEN = os.environ.get("TOKEN")
TELEGRAM_USER = os.environ.get("TELEGRAM_USER")

# Heroku Credentials
APP_URL = os.environ.get("APP_URL")

# Port number for Telegram bot web hook
PORT = int(os.environ.get('PORT', '8443'))


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


# RISK FACTOR
RISK_FACTOR = float(os.environ.get("RISK_FACTOR"))

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

    if len(signal) == 1:
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
            if len(signal[0].split()) == 5:
                trade['trade_id'] = ''
                trade['ordertype'] = (signal[0].split())[3]
                trade['symbol'] = (signal[0].split())[4]
            elif len(signal[0].split()) == 4:
                if (signal[0].split())[3] == 'BUY' or (signal[0].split())[3] == 'SELL':
                    trade['trade_id'] = ''
                    trade['ordertype'] = (signal[0].split())[3]
                    trade['symbol'] = ''
                else:
                    trade['trade_id'] = ''
                    trade['ordertype'] = ''
                    trade['symbol'] = (signal[0].split())[3]
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

        elif('achat' in signal[0].lower()):
            trade['OrderType'] = 'ACHAT'
        
        elif('sell' in signal[0].lower()):
            trade['OrderType'] = 'Sell'

        elif('vente' in signal[0].lower()):
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
            trade['Symbol'] = trade['Symbol'].replace('/','')
            #trade['Symbol'] = trade['Symbol']+"m"
            trade['Entry'] = (signal[2].split(' : '))[-1].replace(' ','')
            trade['Entry'] = float((trade['Entry'].split('-'))[0])

            #trade['StopLoss'] = 0
            #trade['TP'] = [0, 0, 0]

            if(trade['OrderType'] == 'ACHAT'):
                if(len(signal) > 7 and 'TP1'.lower() in signal[4].lower()):
                    trade['TP'] = [float(signal[4].split(' : ')[-1].replace(' ','')), float(signal[5].split(':')[-1].replace(' ','')), trade['Entry'] + 3000]
                    trade['StopLoss'] = float((signal[8].replace(' ','').split(':'))[-1])
                else:
                    trade['TP'] = [trade['Entry'] + 600, trade['Entry'] + 1200, trade['Entry'] + 3000]
                    trade['StopLoss'] = float((signal[6].replace('🔒','').replace(' ','').split(':'))[-1])

            if(trade['OrderType'] == 'VENTE'):
                if(len(signal) > 7 and 'TP1'.lower() in signal[4].lower()):
                    trade['TP'] = [float(signal[4].split(' : ')[-1].replace(' ','')), float(signal[5].split(':')[-1].replace(' ','')), trade['Entry'] - 3000]
                    trade['StopLoss'] = float((signal[8].replace(' ','').split(':'))[-1])
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


            elif('gold' in signal[0].lower()):
                trade['Symbol'] = (signal[0].split())[1]
                trade['Entry'] = float((signal[0].split('-'))[1])
                trade['StopLoss'] = float((signal[2].replace(' ','').split(':'))[-1])
                trade['TP'] = [float((signal[4].replace(' ','').split(':'))[-1])]
                trade['TP'].append(float((signal[5].replace(' ','').split(':'))[-1]))
                
                trade['RiskFactor'] = RISK_FACTOR


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
                    trade['StopLoss'] = float((signal[5].replace(' ','').split('@'))[-1])
                    if(len(signal) > 6 and 'RISK'.lower() in signal[6].lower()):
                        trade['RiskFactor'] = float((signal[6].split())[-1])
                    else:
                        trade['RiskFactor'] = RISK_FACTOR
                else:
                    trade['TP'] = [float((signal[1].replace(' ','').split('@'))[-1])]
                    trade['TP'].append(float(signal[2].replace(' ','').split('@')[-1]))
                    trade['StopLoss'] = float((signal[4].replace(' ','').split('@'))[-1])
                    # checks if there's a TP2 and parses it
                    # if(len(signal) >= 5 and 'tp'.lower() in signal[2].lower()):
                    #     trade['TP'].append(float(signal[2].split()[-1]))
                    #     trade['StopLoss'] = float((signal[4].split())[-1])
                    # else:
                    #     trade['StopLoss'] = float((signal[3].split())[-1])
                    if(len(signal) > 5 and 'RISK'.lower() in signal[5].lower()):
                        trade['RiskFactor'] = float((signal[5].split())[-1])
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

    # pips calculation
    takeProfitPips = []
        
    # calculates the stop loss in pips
    stopLossPips = abs(round((trade['StopLoss'] - trade['Entry']) / multiplier))
    
    #logger.info(stopLossPips)

    if(trade['OrderType'] == 'ACHAT' or trade['OrderType'] == 'VENTE'):
        if currency == 'XOF':
            if(balance <= 301571):
                trade['PositionSize'] = 0.03

            elif(balance > 301571 and balance < 604351):
                trade['PositionSize'] = 0.06

            elif(balance > 604351 and balance < 1208702):
                trade['PositionSize'] = 0.12

            elif(balance > 1208702 and balance < 1813054):
                trade['PositionSize'] = 0.15

            elif(balance > 1813054 and balance < 2417405):
                trade['PositionSize'] = 0.18

            elif(balance > 2417405 and balance < 3021757):
                trade['PositionSize'] = 0.21

            elif(balance > 3021757 and balance < 3626108):
                trade['PositionSize'] = 0.24

            elif(balance > 3626108 and balance < 4230459):
                trade['PositionSize'] = 0.27

            else:
                trade['PositionSize'] = 0.30
                
        else:

            if(balance <= 499):
                trade['PositionSize'] = 0.03

            elif(balance > 499 and balance < 1000):
                trade['PositionSize'] = 0.06

            elif(balance > 1000 and balance < 2000):
                trade['PositionSize'] = 0.12

            elif(balance > 2000 and balance < 3000):
                trade['PositionSize'] = 0.15

            elif(balance > 3000 and balance < 4000):
                trade['PositionSize'] = 0.18

            elif(balance > 4000 and balance < 5000):
                trade['PositionSize'] = 0.21

            elif(balance > 5000 and balance < 6000):
                trade['PositionSize'] = 0.24

            elif(balance > 6000 and balance < 7000):
                trade['PositionSize'] = 0.27

            else:
                trade['PositionSize'] = 0.30


    else:
        if currency == 'XOF':
            #if(balance <= 30228):
            #    trade['PositionSize'] = 0.01
            #else:
            # Conversion de XOF en USD
            amount_usd = xof_to_usd(balance)
            balance = amount_usd

        # calculates the position size using stop loss and RISK FACTOR
        trade['PositionSize'] = math.floor(((balance * trade['RiskFactor']) / stopLossPips) / 10 * 100) / 100

    # calculates the take profit(s) in pips
    for takeProfit in trade['TP']:
        takeProfitPips.append(abs(round((takeProfit - trade['Entry']) / multiplier)))

    #logger.info(takeProfitPips)

    if(trade['OrderType'] != 'ACHAT' and trade['OrderType'] != 'VENTE'):
        # creates table with trade information
        table = CreateTable(trade, balance, stopLossPips, takeProfitPips)
        
        # sends user trade information and calcualted risk
        update.effective_message.reply_text(f'<pre>{table}</pre>', parse_mode=ParseMode.HTML)
        

    return

def CreateTable(trade: dict, balance: float, stopLossPips: int, takeProfitPips: int) -> PrettyTable:
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
    """Edit Stop ongoing trades.

    Arguments:
        update: update from Telegram
    """

    api = MetaApi(API_KEY)
    #messageid = update.effective_message.reply_to_message.message_id

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

        # # Récupérer la connexion à partir du contexte de l'application
        # connection = context.bot_data['mt_streaming_connection']
        # update.effective_message.reply_text(f"CONNECTION: {connection}")

        # obtains account information from MetaTrader server
        #account_information = await connection.get_account_information()

        #logger.info(update.effective_message)
        #logger.info(update.effective_message.reply_to_message)
        #logger.info(update.effective_message.reply_to_message.message_id)

        if update.effective_message.reply_to_message is None:
            if('BE' in update.effective_message.text):
                position = await connection.get_position(trade['trade_id'])
                # Mettre à jour le stop-loss pour qu'il soit égal au niveau de breakeven
                await connection.modify_position(position['id'], stop_loss=position['openPrice'], take_profit=position['takeProfit'])
                update.effective_message.reply_text(f"BreakEven défini pour {position['id']} > {position['type']} {position['symbol']}.")
            else:
                #positions = connection.terminal_state.positions
                positions = await connection.get_positions()
                #logger.info(positions)
                # On vérifie si le symbol est spécifié
                for position in positions:
                    if (not trade['symbol'] and not trade['ordertype']) \
                        or (position['symbol'] == trade['symbol'] and position['type'].endswith(trade['ordertype'])) \
                        or (not trade['symbol'] and position['type'].endswith(trade['ordertype'])) \
                        or (not trade['ordertype'] and position['symbol'] == trade['symbol']):
                        
                        if('BRV' in update.effective_message.text):
                            # Mettre à jour le stop-loss pour qu'il soit égal au niveau du prix d'entré
                            await connection.modify_position(position['id'], stop_loss=position['openPrice'], take_profit=position['takeProfit'])
                            update.effective_message.reply_text(f"BreakEven défini pour {position['id']} > {trade['ordertype']} {position['symbol']}.")
                        elif('SL' in update.effective_message.text and 'TP' in update.effective_message.text):
                            # Mettre à jour le stop-loss pour qu'il soit égal au niveau voulu
                            await connection.modify_position(position['id'], stop_loss=trade['new_sl'], take_profit=trade['new_tp'])
                            update.effective_message.reply_text(f"StopLoss: {trade['new_sl']} & TakeProfit: {trade['new_tp']} définis pour la position {position['id']}.")
                        elif('SL' in update.effective_message.text):
                            # Mettre à jour le stop-loss pour qu'il soit égal au niveau voulu
                            await connection.modify_position(position['id'], stop_loss=trade['newstop'], take_profit=position['takeProfit'])
                            update.effective_message.reply_text(f"StopLoss: {trade['newstop']} défini pour la position {position['id']}.")
                        elif('TP' in update.effective_message.text):
                            # Mettre à jour le take-profit pour qu'il soit égal au niveau voulu
                            await connection.modify_position(position['id'], stop_loss=position['stopLoss'], take_profit=trade['newstop'])
                            update.effective_message.reply_text(f"TakeProfit: {trade['newstop']} défini pour la position {position['id']}.")
                                   
                # else:
                #     await connection.modify_position(position['id'], stop_loss=position['openPrice'], take_profit=position['takeProfit'])
                #     update.effective_message.reply_text(f"BreakEven défini pour toutes les positions.")
        else:
            messageid = update.effective_message.reply_to_message.message_id
            # Appliquez le nouveau Stop Loss sur toutes les positions de la liste
            for position_id in signalInfos_converted[messageid]:
                # Récupérez la position
                position = await connection.get_position(position_id)
                if position is not None:
                    #opening_price = position['openPrice']
                    #takeprofit = position['takeProfit']
                    #stoploss = position['stopLoss']
                    # Mettre à jour le stop-loss pour qu'il soit égal au niveau de breakeven
                    if('BRV' in update.effective_message.text):
                        await connection.modify_position(position_id, stop_loss=position['openPrice'], take_profit=position['takeProfit'])
                        update.effective_message.reply_text(f"BreakEven défini pour la position {position_id}.")
                    elif('SL' in update.effective_message.text and 'TP' in update.effective_message.text):
                        # Mettre à jour le stop-loss pour qu'il soit égal au niveau voulu
                        await connection.modify_position(position_id, stop_loss=trade['new_sl'], take_profit=trade['new_tp'])
                        update.effective_message.reply_text(f"StopLoss: {trade['new_sl']} & TakeProfit: {trade['new_tp']} définis pour la position {position_id}.")
                    elif('SL' in update.effective_message.text):
                        # Mettre à jour le stop-loss pour qu'il soit égal au stoploss voulu
                        await connection.modify_position(position_id, stop_loss=trade['newstop'], take_profit=position['takeProfit'])
                        update.effective_message.reply_text(f"StopLoss: {trade['newstop']} défini pour la position {position_id}.")
                    elif('TP' in update.effective_message.text):
                        # Mettre à jour le stop-loss pour qu'il soit égal au stoploss voulu
                        await connection.modify_position(position_id, stop_loss=position['stopLoss'], take_profit=trade['newstop'])
                        update.effective_message.reply_text(f"TakeProfit: {trade['newstop']} défini pour la position {position_id}.")
        

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
        if(trade['Symbol'] == 'XAUUSD' or trade['Symbol'] == 'XAUEUR' or trade['Symbol'] == 'XAUGBP'):
            multiplier = 0.1

        elif(trade['Symbol'] == 'XAGUSD' or trade['Symbol'] == 'XAGEUR' or trade['Symbol'] == 'XAGGBP'):
            multiplier = 0.001

        elif(trade['Symbol'] in INDICES or trade['Symbol'] in CRYPTO):
            multiplier = 1

        elif(str(trade['Entry']).index('.') >= 2):
            multiplier = 0.01

        else:
            multiplier = 0.0001


        # Symbols editing
        if account_information['broker'] == 'AXSE Brokerage Ltd.':
            trade['Symbol'] = trade['Symbol']+"_raw"
            #logger.info(trade['Symbol'])

        if account_information['server'] == 'Exness-MT5Trial10':
            trade['Symbol'] = trade['Symbol']+"z"
            #logger.info(trade['Symbol'])

        if account_information['broker'] == 'EightCap Global Ltd':
            # Calculer la vrai balance du challenge
            balance = (account_information['balance'] * 5) / 100
            if(multiplier == 1):
                trade['Symbol'] = trade['Symbol']+".b"
            elif(trade['Symbol'] in FOREX):
                trade['Symbol'] = trade['Symbol']+".i"
            #logger.info(trade['Symbol'])
        else:
            balance = account_information['balance']


        # checks if the order is a market execution to get the current price of symbol
        #if(trade['Entry'] == 'NOW' or '-' in trade['Entry']):
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
                        result = await connection.create_market_buy_order(trade['Symbol'], trade['PositionSize'] / len(trade['TP']), trade['StopLoss'], takeProfit)
                        tradeid.append(result['positionId'])

                # executes buy limit order
                elif(trade['OrderType'] == 'Buy Limit'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_limit_buy_order(trade['Symbol'], trade['PositionSize'] / len(trade['TP']), trade['Entry'], trade['StopLoss'], takeProfit)
                        tradeid.append(result['orderId'])

                # executes buy stop order
                elif(trade['OrderType'] == 'Buy Stop'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_stop_buy_order(trade['Symbol'], trade['PositionSize'] / len(trade['TP']), trade['Entry'], trade['StopLoss'], takeProfit)
                        tradeid.append(result['orderId'])

                # executes sell market execution order
                elif(trade['OrderType'] == 'Sell' or trade['OrderType'] == 'VENTE'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_market_sell_order(trade['Symbol'], trade['PositionSize'] / len(trade['TP']), trade['StopLoss'], takeProfit)
                        tradeid.append(result['positionId'])

                # executes sell limit order
                elif(trade['OrderType'] == 'Sell Limit'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_limit_sell_order(trade['Symbol'], trade['PositionSize'] / len(trade['TP']), trade['Entry'], trade['StopLoss'], takeProfit)
                        tradeid.append(result['orderId'])

                # executes sell stop order
                elif(trade['OrderType'] == 'Sell Stop'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_stop_sell_order(trade['Symbol'], trade['PositionSize'] / len(trade['TP']), trade['Entry'], trade['StopLoss'], takeProfit)
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
    """Retrieves information about all ongoing trades.

    Arguments:
        update: update from Telegram
    """
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

        # Fetch open positions
        #positions = connection.terminal_state.positions
        positions = await connection.get_positions()


        if not positions:
            update.effective_message.reply_text("No ongoing trades at the moment.")
            return

        for position in positions:
            # Calculate trade duration
            entry_time = position['time'].strftime('%d-%m-%Y %H:%M:%S')
            #current_time = datetime.utcnow().strftime('%d-%m-%Y %H:%M:%S')
            #duration = current_time - entry_time

            # Extraire jours, heures, minutes et secondes de la durée
            #days = duration.days
            #hours, remainder = divmod(duration.seconds, 3600)  # 3600 secondes dans une heure
            #minutes, seconds = divmod(remainder, 60)  # 60 secondes dans une minute


            trade_info = f"{position['type']}\n" \
                         f"Symbol: {position['symbol']}\n" \
                         f"Volume: {position['volume']}\n" \
                         f"Profit: {position['profit']}\n" \
                         f"ORDER ID: {position['id']}\n\n" \
                         f"Entry Time: {entry_time}\n" \
                         #f"Current Time: {current_time}\n" \
                         #f"Duration: {days} Day(s), {hours}H: {minutes}M: {seconds}S\n" \

            update.effective_message.reply_text(f'<pre>{trade_info}</pre>', parse_mode=ParseMode.HTML)

    except Exception as error:
        logger.error(f'Error: {error}')
        update.effective_message.reply_text(f"Failed to retrieve ongoing trades. Error: {error}")

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
    commands = "List of commands:\n/start : displays welcome message\n/help : displays list of commands and example trades\n/trade : takes in user inputted trade for parsing and placement\n/calculate : calculates trade information for a user inputted trade\n/ongoing_trades : Retrieves information about all ongoing trades.\n"
    trade_example = "Example Trades 💴:\n\n"
    market_execution_example = "Market Execution:\nBUY GBPUSD\nEntry NOW\nSL 1.14336\nTP 1.28930\nTP 1.29845\n\n"
    limit_example = "Limit Execution:\nBUY LIMIT GBPUSD\nEntry 1.14480\nSL 1.14336\nTP 1.28930\n\n"
    note = "You are able to enter up to two take profits. If two are entered, both trades will use half of the position size, and one will use TP1 while the other uses TP2.\n\nNote: Use 'NOW' as the entry to enter a market execution trade."

    # sends messages to user
    update.effective_message.reply_text(help_message)
    update.effective_message.reply_text(commands)
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
    if (len(signal) == 1):
        regex_functions = {
                r"\bPRENEZ LE\b": TakeProfitTrade, # message handler for Take Profit
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
        if (len(signal) == 7):
            regex_functions = {
                    r"\bOuvert\b": PlaceTrade, # message handler for entering trade
                    #r"\bFermez le trade\b": TakeProfitTrade, # message handler for Take Profit the last one        

                    #r"\bRISK\b": PlaceTrade, # message handler for manualy enter trade

            }
        else:
            regex_functions = {
                    #r"\bOuvert\b": PlaceTrade, # message handler for entering trade
                    r"\bFermez le trade\b": TakeProfitTrade, # message handler for Take Profit the last one        

                    r"\bRISK\b": PlaceTrade, # message handler for manualy enter trade

                    #r"\btp\b": PlaceTrade, # message handler for entering trade
                    r"\bSl\b": PlaceTrade, # message handler for entering trade
                    r"\bSL\b": PlaceTrade, # message handler for entering trade
                    #r"\btp2\b": PlaceTrade, # message handler for entering trade
                    #r"\btp 2\b": PlaceTrade, # message handler for entering trade
                    #r"\bTp2\b": PlaceTrade, # message handler for entering trade
                    #r"\bTp 2\b": PlaceTrade, # message handler for entering trade
                    #r"\bSL@\b": PlaceTrade, # message handler for entering trade
                    #r"\b💵TP:\b": PlaceTrade, # message handler for entering trade
                    #r"\b❌SL:\b": PlaceTrade, # message handler for entering trade
                    # r"\bEnter Slowly-Layer\b": PlaceTrade, # message handler for entering trade
            
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
