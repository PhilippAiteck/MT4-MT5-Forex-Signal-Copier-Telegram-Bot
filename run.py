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
SYMBOLS = ['EURUSD.i', 'USDJPY.i', 'GBPUSD.i', 'USDCHF.i', 'AUDUSD.i', 'USDCAD.i', 'NZDUSD.i', 'EURGBP.i', 'EURJPY.i', 'GBPJPY.i', 'AUDJPY.i', 'NZDJPY.i', 'EURAUD.i', 'GBPAUD.i', 'EURNZD.i', 'GBPNZD.i', 'EURCAD.i', 'GBPCAD.i', 'AUDCAD.i', 'NZDCAD.i', 'EURCHF.i', 'GBPCHF.i', 'AUDCHF.i', 'NZDCHF.i', 'USDSEK.i', 'USDDKK.i', 'USDNOK.i', 'USDTRY.i', 'USDMXN.i', 'USDZAR.i', 'EURSEK.i', 'EURDKK.i', 'EURNOK.i', 'EURTRY.i', 'EURMXN.i', 'EURZAR.i', 'GBPSEK.i', 'GBPDKK.i', 'GBPNOK.i', 'GBPTRY.i', 'GBPMXN.i', 'GBPZAR.i', 'AUDSEK.i', 'AUDDKK.i', 'AUDNOK.i', 'AUDTRY.i', 'AUDMXN.i',  'AUDNZD.i','AUDZAR.i', 'CADJPY.i', 'XAUUSD', 'XAGUSD', 'USOIL', 'UKOIL', 'XAUEUR', 'XAUGBP', 'XAGEUR', 'XAGGBP', 'XPTEUR', 'XPTGBP', 'XPDEUR', 'XPDGBP', 'EURUSD', 'USDJPY', 'GBPUSD', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY', 'AUDJPY', 'NZDJPY', 'EURAUD', 'GBPAUD', 'EURNZD', 'GBPNZD', 'EURCAD', 'GBPCAD', 'AUDCAD', 'NZDCAD', 'EURCHF', 'GBPCHF', 'AUDCHF', 'NZDCHF', 'USDSEK', 'USDDKK', 'USDNOK', 'USDTRY', 'USDMXN', 'USDZAR', 'EURSEK', 'EURDKK', 'EURNOK', 'EURTRY', 'EURMXN', 'EURZAR', 'GBPSEK', 'GBPDKK', 'GBPNOK', 'GBPTRY', 'GBPMXN', 'GBPZAR', 'AUDSEK', 'AUDDKK', 'AUDNOK', 'AUDTRY', 'AUDMXN', 'AUDZAR', 'CADJPY', 'AUDNZD', 'XPTUSD.', 'GOLD']
SPECIALSYMBOLS = ['US500Cash', 'US30Cash', 'US100Cash', 'GER40Cash', 'UK100Cash', 'AUS200Cash', 'FRA40Cash', 'JP225Cash', 'SPX500.b', 'US30.b', 'NDX100.b', 'GER30.b', 'UK100.b', 'AUS200.b', 'FRA40.b', 'JPN225.b', 'SPX500', 'US500', 'US30', 'USTEC', 'USTECH', 'NAS100', 'US100', 'GER30', 'UK100', 'AUS200', 'FRA40', 'JP225', 'HK50', 'IN50', 'CN50', 'SG30', 'BTCUSD_raw', 'ETHUSD_raw', 'XRPUSD_raw', 'LTCUSD_raw', 'BTCUSD.b', 'ETHUSD.b', 'XRPUSD.b', 'LTCUSD.b', 'BCHUSD.b', 'ADAUSD.b', 'XLMUSD.b', 'EOSUSD.b', 'XMRUSD.b', 'DASHUSD.b', 'ZECUSD.b', 'BNBUSD.b', 'XTZUSD.b', 'ATOMUSD.b', 'ONTUSD.b', 'NEOUSD.b', 'VETUSD.b', 'ICXUSD.b', 'QTUMUSD.b', 'ZRXUSD.b', 'DOGEUSD.b', 'LINKUSD.b', 'HTUSD.b', 'ETCUSD.b', 'OMGUSD.b', 'NANOUSD.b', 'LSKUSD.b', 'WAVESUSD.b', 'REPUSD.b', 'MKRUSD.b', 'GNTUSD.b', 'LOOMUSD.b', 'MANAUSD.b', 'KNCUSD.b', 'CVCUSD.b', 'BATUSD.b', 'NEXOUSD.b', 'DCRUSD.b', 'PAXUSD.b', 'TUSDUSD.b', 'USDCUSD.b', 'USDTUSD.b', 'BTCUSD', 'ETHUSD', 'XRPUSD', 'LTCUSD', 'BCHUSD', 'ADAUSD', 'XLMUSD', 'EOSUSD', 'XMRUSD', 'DASHUSD', 'ZECUSD', 'BNBUSD', 'XTZUSD', 'ATOMUSD', 'ONTUSD', 'NEOUSD', 'VETUSD', 'ICXUSD', 'QTUMUSD', 'ZRXUSD', 'DOGEUSD', 'LINKUSD', 'HTUSD', 'ETCUSD', 'OMGUSD', 'NANOUSD', 'LSKUSD', 'WAVESUSD', 'REPUSD', 'MKRUSD', 'GNTUSD', 'LOOMUSD', 'MANAUSD', 'KNCUSD', 'CVCUSD', 'BATUSD', 'NEXOUSD', 'DCRUSD', 'PAXUSD', 'TUSDUSD', 'USDCUSD', 'USDTUSD', 'BTCUSDm']

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

    # determines the order type of the trade
    if('Buy Limit'.lower() in signal[0].lower()):
        trade['OrderType'] = 'Buy Limit'

    elif('Sell Limit'.lower() in signal[0].lower()):
        trade['OrderType'] = 'Sell Limit'

    elif('Buy Stop'.lower() in signal[0].lower()):
        trade['OrderType'] = 'Buy Stop'

    elif('Sell Stop'.lower() in signal[0].lower()):
        trade['OrderType'] = 'Sell Stop'

    elif('Buy'.lower() in signal[0].lower()):
        trade['OrderType'] = 'Buy'

    elif('ACHAT'.lower() in signal[0].lower()):
        trade['OrderType'] = 'ACHAT'
    
    elif('Sell'.lower() in signal[0].lower()):
        trade['OrderType'] = 'Sell'

    elif('VENTE'.lower() in signal[0].lower()):
        trade['OrderType'] = 'VENTE'
    
    # returns an empty dictionary if an invalid order type was given
    else:
        return {}

    # extracts symbol from trade signal
    trade['Symbol'] = (signal[0].split())[-1]
    if('(' in trade['Symbol'] or ')' in trade['Symbol']):
        trade['Symbol'] = (signal[0].split())[-2]
        #logger.info(trade['Symbol'])
        
    if('/' in trade['Symbol']):
        trade['Symbol'] = trade['Symbol'].replace('/','')
        #logger.info(trade['Symbol'])
    
    # checks if the symbol is valid, if not, returns an empty dictionary
    #if((trade['Symbol'] not in SYMBOLS) and (trade['Symbol'] not in SPECIALSYMBOLS)):
    #    return {}
    
    # checks wheter or not to convert entry to float because of market exectution option ("NOW")
    #if(trade['OrderType'] == 'Buy' or trade['OrderType'] == 'Sell'):
    #    trade['Entry'] = (signal[1].split())[-1]

    # checks if it's market exectution option ACHAT or VENTE to extract null: PE, SL and TP
    if(trade['OrderType'] == 'ACHAT' or trade['OrderType'] == 'VENTE'):
        trade['Entry'] = (signal[2].split(' : '))[-1].replace(' ','')
        trade['Entry'] = float((trade['Entry'].split('-'))[0])
        #trade['StopLoss'] = 0
        #trade['TP'] = [0, 0, 0]

        if(trade['OrderType'] == 'ACHAT'):
            trade['StopLoss'] = float(trade['Entry'] - 1000)
            trade['TP'] = [trade['Entry'] + 800, trade['Entry'] + 1600, trade['Entry'] + 4000]

        if(trade['OrderType'] == 'VENTE'):
            trade['StopLoss'] = float(trade['Entry'] + 1000)
            trade['TP'] = [trade['Entry'] - 800, trade['Entry'] - 1600, trade['Entry'] - 4000]

    else:
        trade['Entry'] = float((signal[1].split())[-1])

        trade['StopLoss'] = float((signal[2].split())[-1])
        trade['TP'] = [float((signal[3].split())[-1])]

        # checks if there's a fourth line and parses it for TP2
        if(len(signal) > 4):
            trade['TP'].append(float(signal[4].split()[-1]))
            
        # checks if there's a fith line and parses it for TP3
        if(len(signal) > 5):
            trade['TP'].append(float(signal[5].split()[-1]))

    # adds risk factor to trade
    trade['RiskFactor'] = RISK_FACTOR

    return trade

def GetTradeInformation(update: Update, trade: dict, balance: float, currency: str) -> None:
    """Calculates information from given trade including stop loss and take profit in pips, posiition size, and potential loss/profit.

    Arguments:
        update: update from Telegram
        trade: dictionary that stores trade information
        balance: current balance of the MetaTrader account
        currency: currency of the MetaTrader account
    """

    # calculates the stop loss in pips
    if(trade['Symbol'] == 'XAUUSD' or trade['Symbol'] == 'GOLD' or trade['Symbol'] == 'XAUUSD_raw'):
        multiplier = 0.1

    elif(trade['Symbol'] == 'XAGUSD'):
        multiplier = 0.001

    elif(trade['Symbol'] in SPECIALSYMBOLS):
        multiplier = 1

    elif(str(trade['Entry']).index('.') >= 2):
        multiplier = 0.01

    else:
        multiplier = 0.0001

    # pips calculation
    takeProfitPips = []
        
    # calculates the stop loss in pips
    stopLossPips = abs(round((trade['StopLoss'] - trade['Entry']) / multiplier))

    if(trade['OrderType'] == 'ACHAT' or trade['OrderType'] == 'VENTE'):
        if currency == 'XOF':
            if(balance <= 296000):
                trade['PositionSize'] = 0.03

            elif(balance > 296000 and balance < 593000):
                trade['PositionSize'] = 0.06

            else:
                trade['PositionSize'] = 0.09

        else:

            if(balance <= 499):
                trade['PositionSize'] = 0.03

            elif(balance > 499 and balance < 1000):
                trade['PositionSize'] = 0.06

            else:
                trade['PositionSize'] = 0.09

    else:

        # calculates the position size using stop loss and RISK FACTOR
        trade['PositionSize'] = math.floor(((balance * trade['RiskFactor']) / stopLossPips) / 10 * 100) / 100

    # calculates the take profit(s) in pips
    for takeProfit in trade['TP']:
        takeProfitPips.append(abs(round((takeProfit - trade['Entry']) / multiplier)))


    #logger.info(stopLossPips)
    #logger.info(takeProfitPips)

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



async def CloseTrade(update: Update, trade_id, signalInfos_converted) -> None:
    """Close ongoing trades.

    Arguments:
        update: update from Telegram
    """
    api = MetaApi(API_KEY)
    messageid = update.effective_message.reply_to_message.message_id
    update.effective_message.reply_text(signalInfos_converted)

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

        result = await connection.close_position(trade_id)
        update.effective_message.reply_text(f"Position {trade_id} fermée avec succes 'TP' 💰.")

        if('TP1'.lower() in update.effective_message.text.lower()):
            # Appliquez un breakeven pour les deux dernières positions de la liste
            for position_id in signalInfos_converted[messageid][1:]:
                # Récupérez la position
                position = await connection.get_position(position_id)
                if position is not None:
                    opening_price = position['openPrice']
                    take_profit = position['takeProfit']
                    await connection.modify_position(position_id, stop_loss=opening_price, take_profit=take_profit)
                    update.effective_message.reply_text(f"Breakeven défini pour la position {position_id}.")
                else:
                    update.effective_message.reply_text(f"La position {position_id} n'a pas été trouvée.")


        return result

    except Exception as error:
        logger.error(f'Error: {error}')
        update.effective_message.reply_text(f"Failed to close trades. Error: {error}")


async def MoveToBreakEven(update: Update, signalInfos_converted: dict):
    """Break-even ongoing trades.

    Arguments:
        update: update from Telegram
    """
 
    api = MetaApi(API_KEY)
    messageid = update.effective_message.reply_to_message.message_id

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
        
        if('TP1'.lower() in update.effective_message.text.lower()):
            # Appliquez un breakeven pour les deux dernières positions de la liste
            for position_id in signalInfos_converted[messageid][1:]:
                # Récupérez la position
                position = await connection.get_position(position_id)
                if position is not None:
                    opening_price = position['openPrice']
                    take_profit = position['takeProfit']
                    await connection.modify_position(position_id, stop_loss=opening_price, take_profit=take_profit)
                    update.effective_message.reply_text(f"Breakeven défini pour la position {position_id}.")
                else:
                    update.effective_message.reply_text(f"La position {position_id} n'a pas été trouvée.")
   
    except Exception as error:
        logger.error(f'Error: {error}')
        update.effective_message.reply_text(f"Failed to break-even the trades. Error: {error}")


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

        if account_information['broker'] == 'AXSE Brokerage Ltd.':
            trade['Symbol'] = trade['Symbol']+"_raw"
            logger.info(trade['Symbol'])


        update.effective_message.reply_text("Successfully connected to MetaTrader!\nCalculating trade risk ... 🤔")


         # Ajout de la logique pour la fermeture du trade et le breakeven
        if 'close_trade_id' in trade:
            result_close = await CloseTrade(connection, trade['close_trade_id'])
            update.effective_message.reply_text(f"Trade closed! Result: {result_close}")

        if 'move_to_break_even' in trade:
            break_even_price = trade['move_to_break_even']
            result_be = await MoveToBreakEven(connection, trade['move_to_break_even']['trade_id'], break_even_price)
            update.effective_message.reply_text(f"Moved to breakeven! Result: {result_be}")


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
        GetTradeInformation(update, trade, account_information['balance'], account_information['currency'])
            
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

    #logger.info(update.effective_message.reply_to_message.message_id)

    # checks if the trade has already been parsed or not
    #if(context.user_data['trade'] == None):

    messageid = update.effective_message.reply_to_message.message_id
    signalInfos = read_data_from_json()
    trade_id = 0

    # Convertir les valeurs de type chaîne en entiers
    signalInfos_converted = {int(key): value for key, value in signalInfos.items()}
    #update.effective_message.reply_text(signalInfos_converted)

    # Sérialisation des clés "key"
    cles_serializables = list(signalInfos_converted.keys())

    try: 

        # parses signal from Telegram message and determines the trade to close 
        if('TP1'.lower() in update.effective_message.text.lower() and messageid in cles_serializables):
            trade_id = signalInfos_converted[messageid][0]
            
        elif('TP2'.lower() in update.effective_message.text.lower() and messageid in cles_serializables):
            trade_id = signalInfos_converted[messageid][1]

        elif('Fermez le trade'.lower() in update.effective_message.text.lower() and messageid in cles_serializables):
            trade_id = signalInfos_converted[messageid][2]


        # Fermez la position de la liste
        resultclose = asyncio.run(CloseTrade(update, trade_id, signalInfos_converted))
        
        # Appliquez un breakeven pour les deux dernières positions de la liste
        #resultBE = asyncio.run(MoveToBreakEven(update, signalInfos_converted))

        # checks if there was an issue with parsing the trade
        #if(not(signalInfos)):
        #    raise Exception('Invalid Close Signal')

    
    except Exception as error:
        logger.error(f'Error: {error}')
        errorMessage = f"There was an error parsing this signal 😕\n\nError: {error}\n\n"
        update.effective_message.reply_text(errorMessage)

        # returns to TRADE state to reattempt trade parsing
        return TRADE
    
    # attempts connection to MetaTrader and take some profit
    #resultclose = asyncio.run(CloseTrade(update, trade_id))
    #update.effective_message.reply_text(resultclose)

    #  # Fermez la première position de la liste
    # if signalInfos_converted:
    #     #await connection.close_position(trade_id)
    #     resultclose = asyncio.run(CloseTrade(update, trade_id))
    #     update.effective_message.reply_text((f"Position {trade_id} fermée avec succes 💰."))
    # else:
    #     update.effective_message.reply_text(("Aucune position à fermer."))

    # # Appliquez un breakeven pour les deux dernières positions de la liste
    # for position_id in signalInfos_converted[messageid][1:]:
    #     # Récupérez les informations de la position pour définir un breakeven
    #     resultBE = asyncio.run(MoveToBreakEven(update, position_id))

    # set the break-even on the other positions
    #resultBE = asyncio.run(MoveToBreakEven(update, trade_id))
    #update.effective_message.reply_text(resultBE)

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

# Fonction pour gérer les messages
def handle_message(update, context):
    text_received = update.message.text

    # Liste des expressions régulières et fonctions associées
    regex_functions = {
        r"\bBTC/USD\b": PlaceTrade, # message handler for entering trade
        r"\bPRENEZ LE\b": TakeProfitTrade, # message handler to Take Profit
        r"\bFermez le trade maintenant\b": TakeProfitTrade, # message handler to Take Profit the last one
        # r"\bMETTRE LE SL\b": EditTrade, # message handler for edit SL
        # Ajoutez d'autres regex et fonctions associées ici
    }

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

# Fonction pour envoyer périodiquement le message
def periodic_message(update, context):
    chat_id = update.message.chat_id  # Remplacez par l'ID du chat où vous souhaitez envoyer le message
    message_text = 'Message à envoyer toutes les 5 minutes'
    context.bot.send_message(chat_id=chat_id, text=message_text)

# Fonction pour envoyer un message
def send_message(update, context):
    chat_id = update.message.chat_id
    message_text = 'Message à envoyer toutes les 5 minutes'
    context.bot.send_message(chat_id=chat_id, text=message_text)


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
    #dp.add_handler(CommandHandler("open_trades", GetOpenTradeIDs))

    # conversation handler for entering trade or calculating trade information
    dp.add_handler(conv_handler)

    # Définir le handler de commande pour déclencher l'envoi de message
    dp.add_handler(CommandHandler('sendmessage', send_message))

   # message handler for all messages that are not included in conversation handler
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

 
    # log all errors
    dp.add_error_handler(error)
    
    # listens for incoming updates from Telegram
    updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=APP_URL + TOKEN)
    updater.idle()

    # Planification de l'envoi du message toutes les 5 minutes
    updater.job_queue.run_repeating(periodic_message, interval=300, first=0)

    #threading.Timer(5.0, update.effective_message.reply_text(update.effective_message.message_id)).start()

    return


if __name__ == '__main__':
    main()
