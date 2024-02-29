#!/usr/bin/env python3
import asyncio
import logging
import math
import os
import re
import json

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

    trade = {}


    if('METTRE LE SL'.lower() in signal[0].lower()):
        # extract the StopLoss
        trade['stoploss'] = float(((signal[0].split())[4]) + ((signal[0].split())[5]))
        #trade['ordertype'] = (signal[0].split())[-3]
    elif('CLOTURE' in signal[0] or 'BE' in signal[0]):
        if len(signal[0].split()) >= 3:
            trade['ordertype'] = (signal[0].split())[1]
            trade['symbol'] = (signal[0].split())[2]
        elif len(signal[0].split()) >= 2:
            if (signal[0].split())[1] == 'BUY' or (signal[0].split())[1] == 'SELL':
                trade['ordertype'] = (signal[0].split())[1]
                trade['symbol'] = ''
            else:
                trade['ordertype'] = ''
                trade['symbol'] = (signal[0].split())[1]
        else:
            trade['symbol'] = ''
            trade['ordertype'] = ''

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

            trade['StopLoss'] = 0
            #trade['TP'] = [0, 0, 0]

            if(trade['OrderType'] == 'ACHAT'):
                #trade['StopLoss'] = float(trade['Entry'] - 1500)
                trade['TP'] = [trade['Entry'] + 1000, trade['Entry'] + 2000, trade['Entry'] + 3000]

            if(trade['OrderType'] == 'VENTE'):
                #trade['StopLoss'] = float(trade['Entry'] + 1500)
                trade['TP'] = [trade['Entry'] - 1000, trade['Entry'] - 2000, trade['Entry'] - 3000]

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

            elif('Tp @'.lower() in signal[3].lower()):
                if('limit'.lower() in trade['OrderType'].lower()):
                    if('for'.lower() in signal[0]):
                        trade['Symbol'] = (signal[0].split())[3]
                    else:
                        trade['Symbol'] = (signal[0].split())[0]
                        #trade['Entry'] = float((signal[0].split())[-1])
                else:
                    trade['Symbol'] = (signal[0].split())[1]
                if('#'.lower() in trade['Symbol'].lower()):
                    trade['Symbol'].replace('#','')
                trade['Entry'] = (signal[0].split())[-1]
                trade['StopLoss'] = float((signal[2].replace(' ','').split('@'))[-1])
                trade['TP'] = [float((signal[3].replace(' ','').split('@'))[-1])]
                if('tp2' in signal[4].lower()):
                    trade['TP'].append(float((signal[4].replace(' ','').split('@'))[-1]))

            elif('slowly-layer'.lower() in signal[7].lower()):
                trade['Symbol'] = (signal[0].split())[1]
                trade['Entry'] = float((signal[0].split('-'))[1])
                trade['StopLoss'] = float((signal[2].replace(' ','').split(':'))[-1])
                trade['TP'] = [float((signal[4].replace(' ','').split(':'))[-1])]
                trade['TP'].append(float((signal[5].replace(' ','').split(':'))[-1]))

        if(trade['Symbol'].lower() == 'gold'): 
            trade['Symbol'] = 'XAUUSD'
    
        # adds risk factor to trade
        trade['RiskFactor'] = RISK_FACTOR

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



async def CloseTrade(update: Update, trade: dict, trade_id, signalInfos_converted) -> None:
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

        # Fetch profit of the position
        #position = await connection.get_history_orders_by_position(position_id=trade_id)
        #profit = position['profit']

        if update.effective_message.reply_to_message is None and trade_id == 0:
            positions = await connection.get_positions()
            for position in positions:
                if (not trade['symbol'] and not trade['ordertype']) \
                    or (position['symbol'] == trade['symbol'] and position['type'].endswith(trade['ordertype'])) \
                    or (not trade['symbol'] and position['type'].endswith(trade['ordertype'])) \
                    or (not trade['ordertype'] and position['symbol'] == trade['symbol']):
                    # Fermez la ou les position(s)  
                    result = await connection.close_position(position['id'])
                    update.effective_message.reply_text(f"Position {position['id']} > {trade['ordertype']} {position['symbol']} fermée avec succes.")
                    logger.info(result)

        elif update.effective_message.reply_to_message is not None and trade_id == 0:
            messageid = update.effective_message.reply_to_message.message_id
            # Fermez toutes les positions de la liste
            for position_id in signalInfos_converted[messageid]:
                # Close the position
                result = await connection.close_position(position_id)
                update.effective_message.reply_text(f"Position {position_id} fermée avec succes.")
                logger.info(result)

        else:
            # Close the position
            result = await connection.close_position(trade_id)
            update.effective_message.reply_text(f"Position {trade_id} fermée avec succes. 💰")

            if('TP1'.lower() in update.effective_message.text.lower()):
                messageid = update.effective_message.reply_to_message.message_id
                # Appliquez un breakeven pour les deux dernières positions de la liste
                for position_id in signalInfos_converted[messageid][1:]:
                    # Récupérez la position
                    position = await connection.get_position(position_id)
                    if position is not None:
                        opening_price = position['openPrice']
                        takeprofit = position['takeProfit']
                        await connection.modify_position(position_id, stop_loss=opening_price, take_profit=takeprofit)
                        update.effective_message.reply_text(f"Breakeven défini pour la position {position_id}.")
                    else:
                        update.effective_message.reply_text(f"La position {position_id} n'a pas été trouvée.")


        return result

    except Exception as error:
        logger.error(f'Error: {error}')
        update.effective_message.reply_text(f"Failed to close trades. Error: {error}")


async def EditTrade(update: Update, trade: dict, signalInfos_converted):
    """Edit SL ongoing trades.

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

        # obtains account information from MetaTrader server
        #account_information = await connection.get_account_information()

        #logger.info(update.effective_message)
        #logger.info(update.effective_message.reply_to_message)
        #logger.info(update.effective_message.reply_to_message.message_id)

        if update.effective_message.reply_to_message is None:
            positions = await connection.get_positions()
            # On vérifie si le symbol est spécifié
            for position in positions:
                if (not trade['symbol'] and not trade['ordertype']) \
                    or (position['symbol'] == trade['symbol'] and position['type'].endswith(trade['ordertype'])) \
                    or (not trade['symbol'] and position['type'].endswith(trade['ordertype'])) \
                    or (not trade['ordertype'] and position['symbol'] == trade['symbol']):
                    # Mettre à jour le stop-loss pour qu'il soit égal au niveau de breakeven
                    await connection.modify_position(position['id'], stop_loss=position['openPrice'], take_profit=position['takeProfit'])
                    update.effective_message.reply_text(f"BreakEven défini pour {position['id']} > {trade['ordertype']} {position['symbol']}.")
            else:
                update.effective_message.reply_text(f"Aucune position n'est ouverte")
                                
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
                    opening_price = position['openPrice']
                    takeprofit = position['takeProfit']
                    # Mettre à jour le stop-loss pour qu'il soit égal au niveau de breakeven
                    if('BE' in update.effective_message.text):
                        await connection.modify_position(position_id, stop_loss=opening_price, take_profit=takeprofit)
                        update.effective_message.reply_text(f"BreakEven défini pour la position {position_id}.")
                    else:
                        # Mettre à jour le stop-loss pour qu'il soit égal au stoploss voulu
                        await connection.modify_position(position_id, stop_loss=trade['stoploss'], take_profit=takeprofit)
                        update.effective_message.reply_text(f"SL défini pour la position {position_id}.")
                else:
                    update.effective_message.reply_text(f"La position n'a pas été trouvée.")
        

    except Exception as error:
        logger.error(f'Error: {error}')
        update.effective_message.reply_text(f"Failed to set new SL on the trades. Error: {error}")


async def ConnectMetaTrader(update: Update, trade: dict, enterTrade: bool):
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


        # obtains account information from MetaTrader server
        account_information = await connection.get_account_information()

        update.effective_message.reply_text("Successfully connected to MetaTrader!\nCalculating trade risk ... 🤔")


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

                # executes buy stop order
                elif(trade['OrderType'] == 'Buy Stop'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_stop_buy_order(trade['Symbol'], trade['PositionSize'] / len(trade['TP']), trade['Entry'], trade['StopLoss'], takeProfit)

                # executes sell market execution order
                elif(trade['OrderType'] == 'Sell' or trade['OrderType'] == 'VENTE'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_market_sell_order(trade['Symbol'], trade['PositionSize'] / len(trade['TP']), trade['StopLoss'], takeProfit)
                        tradeid.append(result['positionId'])

                # executes sell limit order
                elif(trade['OrderType'] == 'Sell Limit'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_limit_sell_order(trade['Symbol'], trade['PositionSize'] / len(trade['TP']), trade['Entry'], trade['StopLoss'], takeProfit)

                # executes sell stop order
                elif(trade['OrderType'] == 'Sell Stop'):
                    for takeProfit in trade['TP']:
                        result = await connection.create_stop_sell_order(trade['Symbol'], trade['PositionSize'] / len(trade['TP']), trade['Entry'], trade['StopLoss'], takeProfit)
                
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


async def GetOngoingTrades(update: Update, context: CallbackContext) -> None:
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

        update.effective_message.reply_text("Successfully connected to MetaTrader! 👍🏾 \nRetrieving all ongoing trades ...")

        # Fetch open positions
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
    #if(context.user_data['trade'] == None):
    try: 
        # parses signal from Telegram message
        trade = ParseSignal(update.effective_message.text)
        
        # checks if there was an issue with parsing the trade
        if(not(trade)):
            raise Exception('Invalid Trade')

        # sets the user context trade equal to the parsed trade and extract messageID 
        context.user_data['trade'] = trade
        update.effective_message.reply_text("Trade Successfully Parsed! 🥳\nConnecting to MetaTrader ... \n(May take a while) ⏰")
    
    except Exception as error:
        logger.error(f'Error: {error}')
        errorMessage = f"There was an error parsing this trade 😕\n\nError: {error}\n\nPlease re-enter trade with this format:\n\nBUY/SELL SYMBOL\nEntry \nSL \nTP \n\nOr use the /cancel to command to cancel this action."
        update.effective_message.reply_text(errorMessage)

        # returns to TRADE state to reattempt trade parsing
        return TRADE
    
    signalInfos = read_data_from_json()
    
    # extraction of the signal messageID's 
    if update.effective_message.message_id not in signalInfos:
        signalInfos[update.effective_message.message_id] = []

    # attempts connection to MetaTrader and places trade
    tradeid = asyncio.run(ConnectMetaTrader(update, context.user_data['trade'], True))

    # adding tradeid values in signalInfos
    signalInfos[update.effective_message.message_id].extend(tradeid)
    #signalInfos.update(signalInfos[update.effective_message.message_id].extend(tradeid))
    #update.effective_message.reply_text(signalInfos)

    write_data_to_json(signalInfos)
    
    # removes trade from user context data
    context.user_data['trade'] = None

    return ConversationHandler.END

def CalculateTrade(update: Update, context: CallbackContext) -> int:
    """Parses trade and places on MetaTrader account.   
    
    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks
    """

    # checks if the trade has already been parsed or not
    if(context.user_data['trade'] == None):

        try: 
            # parses signal from Telegram message
            trade = ParseSignal(update.effective_message.text)
            
            # checks if there was an issue with parsing the trade
            if(not(trade)):
                raise Exception('Invalid Trade')

            # sets the user context trade equal to the parsed trade
            context.user_data['trade'] = trade
            update.effective_message.reply_text("Trade Successfully Parsed! 🥳\nConnecting to MetaTrader ... (May take a while) ⏰")
        
        except Exception as error:
            logger.error(f'Error: {error}')
            errorMessage = f"There was an error parsing this trade 😕\n\nError: {error}\n\nPlease re-enter trade with this format:\n\nBUY/SELL SYMBOL\nEntry \nSL \nTP \n\nOr use the /cancel to command to cancel this action."
            update.effective_message.reply_text(errorMessage)

            # returns to CALCULATE to reattempt trade parsing
            return CALCULATE
    
    # attempts connection to MetaTrader and calculates trade information
    asyncio.run(ConnectMetaTrader(update, context.user_data['trade'], False))

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
    #if(context.user_data['trade'] == None):

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
        resultclose = asyncio.run(CloseTrade(update, trade, trade_id, signalInfos_converted))
        
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
    context.user_data['trade'] = None

    return ConversationHandler.END

def EditStopLossTrade(update: Update, context: CallbackContext) -> int:
    """Starts process of parsing TP signal and closing trade on MetaTrader account.

    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks

    """

    # checks if the trade has already been parsed or not
    #if(context.user_data['trade'] == None):

    #messageid = update.effective_message.reply_to_message.message_id
    signalInfos = read_data_from_json()

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
        context.user_data['trade'] = trade
        update.effective_message.reply_text("Signal Successfully Parsed! 🥳\nConnecting to MetaTrader ... \n(May take a while) ⏰")
       
        # checks if there was an issue with parsing the trade
        #if(not(signalInfos)):
        #    raise Exception('Invalid Close Signal')

    
    except Exception as error:
        logger.error(f'Error: {error}')
        errorMessage = f"There was an error parsing this signal 😕\n\nError: {error}\n\n"
        update.effective_message.reply_text(errorMessage)

        # returns to TRADE state to reattempt trade parsing
        return TRADE
    
    # Modifiez le stoploss des positions de la liste
    resultedit = asyncio.run(EditTrade(update, trade, signalInfos_converted))
 
    # removes trade from user context data
    context.user_data['trade'] = None

    return ConversationHandler.END

def CloseAllTrade(update: Update, context: CallbackContext) -> int:
    """Starts process of parsing TP signal and closing trade on MetaTrader account.

    Arguments:
        update: update from Telegram
        context: CallbackContext object that stores commonly used objects in handler callbacks

    """

    # checks if the trade has already been parsed or not
    #if(context.user_data['trade'] == None):

    #messageid = update.effective_message.reply_to_message.message_id
    signalInfos = read_data_from_json()
    trade_id = 0


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
            raise Exception('Invalid close signal')

        # sets the user context trade equal to the parsed trade and extract messageID 
        context.user_data['trade'] = trade
        update.effective_message.reply_text("Signal Successfully Parsed! 🥳\nConnecting to MetaTrader ... \n(May take a while) ⏰")
       
        # checks if there was an issue with parsing the trade
        #if(not(signalInfos)):
        #    raise Exception('Invalid Close Signal')

    
    except Exception as error:
        logger.error(f'Error: {error}')
        errorMessage = f"There was an error parsing this signal 😕\n\nError: {error}\n\n"
        update.effective_message.reply_text(errorMessage)

        # returns to TRADE state to reattempt trade parsing
        return TRADE
    
    # Modifiez le stoploss des positions de la liste
    resultclose = asyncio.run(CloseTrade(update, trade, trade_id, signalInfos_converted))
 
    # removes trade from user context data
    context.user_data['trade'] = None

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
    context.user_data['trade'] = None

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
    context.user_data['trade'] = None
    
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
    context.user_data['trade'] = None

    # asks user to enter the trade
    update.effective_message.reply_text("Please enter the trade that you would like to calculate.")

    return CALCULATE

def GetOpenTradeIDs(update: Update, context: CallbackContext):
    """Retrieves information about all ongoing trades.

    Arguments:
        update: update from Telegram
    """

    # attempts connection to MetaTrader and retreive ongoing trade
    asyncio.run(GetOngoingTrades(update, context))

    return

def GetMessageTradeIDs(update: Update, context: CallbackContext):
    """Retrieves information about all trades's ID with their message ID .

    """
    # Retrieves all trades's ID with their message ID from son file.
    signalInfos = read_data_from_json()

    update.effective_message.reply_text(signalInfos)

# Fonction pour gérer les messages
def handle_message(update, context):
    text_received = update.message.text
    #chat_title = update.message.forward_from_chat.title

    # Liste des expressions régulières et fonctions associées
    regex_functions = {
        r"\bBTC/USD\b": PlaceTrade, # message handler for entering trade
        r"\bTP\b": PlaceTrade, # message handler for entering trade
        r"\bEnter Slowly-Layer\b": PlaceTrade, # message handler for entering trade

        r"\bPRENEZ LE\b": TakeProfitTrade, # message handler to Take Profit
        r"\bFermez le trade\b": TakeProfitTrade, # message handler to Take Profit the last one
        r"\bSECURE PARTIALS\b": TakeProfitTrade, # message handler to Take Profit
        
        r"\bMETTRE LE SL\b": EditStopLossTrade, # message handler for edit SL
        r"\bBE\b": EditStopLossTrade, # message handler for edit SL

        r"\bCLOSE ALL\b": CloseAllTrade, # message handler to Take Profit

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

def main() -> None:
    """Runs the Telegram bot."""

    updater = Updater(TOKEN, use_context=True)

    # get the dispatcher to register handlers
    dp = updater.dispatcher

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
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    #dp.add_handler(MessageHandler(Filters.text & ~Filters.command, periodic_handler))


    # log all errors
    dp.add_error_handler(error)
    
    # listens for incoming updates from Telegram
    updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=APP_URL + TOKEN)
    updater.idle()

    return


if __name__ == '__main__':
    main()
