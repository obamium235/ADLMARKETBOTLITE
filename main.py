import requests
import schedule
import time
import os.path
import pickle
import colorama
from steampy.client import SteamClient
import authdata
from steampy import guard
import logging

colorama.init()
logging.basicConfig(level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S',format='[%(asctime)s] %(message)s')
log = logging.getLogger('main')
steam_client = SteamClient(authdata.api_key)

# i know, globals is bad, yeah
is_have_trade_tm = False
is_updating_tm_inv = False
is_checking_tm_inv = False
tm_errors_count = 0
do_trade_action = ''

def log_in_steam():
    # Shitty hack for cookie caching right here
    # imagine the smell, mmmmm
    if os.path.exists('./main.dat'):
        if os.path.isfile('./main.dat'):
            try:
                with open('./main.dat', "rb") as f:
                    steam_client._session.cookies._cookies = pickle.load(f)
                log.info('loaded cookies from file')
            except Exception as e:
                log.warn('loading cookies from file failed: %s', repr(e))
    else:
        log.info('cookie file not found, will create later')

    steam_client.was_login_executed = True
    steam_client.username = authdata.login
    steam_client._password = authdata.password
    steam_client.steam_guard = guard.load_steam_guard("guard.json")
    if steam_client.is_session_alive():
        log.info('session is alive, no need to relogin')
        return
    else:
        log.info('no, session is kill, need to (re)login')
        steam_client.was_login_executed = False

    log.info('login in Steam...')
    try:
        steam_client.login(authdata.login, authdata.password, "guard.json")
    except Exception as e:
        log.critical('fatal steam login error: %s', repr(e))
        log.critical('quit...')
        exit(1)
    else:
        log.info('logged into Steam, saving cookies...')
        with open('./main.dat', "wb") as f:
            pickle.dump(steam_client._session.cookies._cookies, f)

def check_trade():
    log.info("checking if we have any trades on Steam-trader")
    try:
        res_trader = requests.get(f"https://api.steam-trader.com/exchange/?key={authdata.trader_api}")
    except Exception as e:
        log.error("Steam-trader request failed: %s", repr(e))

    try:
        res_trade_json = res_trader.json()
    except Exception as e:
        log.error("Steam-trader response parsing failed: %s", repr(e))
    else:
        try_amount = 10

        success_steamtrader = res_trade_json.get("success", "")
        errcode_steamtrader = res_trade_json.get("code", "")
        errstr__steamtrader = res_trade_json.get("error", "")
        if success_steamtrader:
            offer = res_trade_json["offerId"]
            log.info('got trade offer: %s', offer)
            trade_accepted = False
            while not trade_accepted:
                try:
                    steam_client.accept_trade_offer(str(offer))
                    trade_accepted = True
                    log.info("tradeoffer %s accepted", offer)
                except Exception as e:
                    log.error("error accepting trade offer %s : %s", offer, repr(e))
                    if try_amount < 0:
                        log.error("giving up on accepting trade offer %s", offer)
                        break
                    log.error("retry to accept trade offer %s (attempt %s/%s)", offer, 10-try_amount, try_amount)
                    try_amount -= 1
                    time.sleep(10)
        elif success_steamtrader == False and errcode_steamtrader == 4:
            log.info("nothing to trade right now")
        elif success_steamtrader == False:
            log.warn("Steam-trader exchange error: %s (%s)", errstr__steamtrader, errcode_steamtrader)
        else:
            log.warn('wut?')
            print(res_trader.text)

def session_ok():
    try:
        is_alive = steam_client.is_session_alive()
    except Exception as e:
        log.error("Steam session check failed: %s", repr(e))
        time.sleep(5)
        session_ok()
    else:
        if is_alive:
            log.info('Steam session is OK, waiting for trades')
        else:
            log.info('Steam session expired, doing relogin')
            log_in_steam()

def ping_tm():
    try:
        tm_response = requests.get(f"https://tf2.tm/api/v2/ping/?key={authdata.tm_api}")
    except Exception as e:
        log.error("tm ping request failed: %s", repr(e))
    if tm_response.text.find('<html') >=0 and tm_response.text.find('Engineering works') >=0:
        log.warn('tm error: Engineering works')
        return
    try:
        tm_response_json = tm_response.json()
    except Exception as e:
        log.error("tm ping response parsing failed: %s", repr(e))
    else:
        success_tm = tm_response_json.get("success", "")
        errstr__tm = tm_response_json.get("error", "") or tm_response_json.get("message", "")
        if success_tm:
            log.info('pinged tm')
        else:
            log.warn("tm ping error: %s", errstr__tm)

def do_update_tm_inv():
    global is_updating_tm_inv, is_checking_tm_inv
    if is_updating_tm_inv and not is_checking_tm_inv:
        try:
            tm_response = requests.get(f"https://tf2.tm/api/v2/update-inventory/?key={authdata.tm_api}")
        except Exception as e:
            log.error("tm update inv request failed: %s", repr(e))
        if tm_response.text.find('<html') >=0 and tm_response.text.find('Engineering works') >=0:
            log.warn('tm error: Engineering works')
            return
        try:
            tm_response_json = tm_response.json()
        except Exception as e:
            log.error("tm update inv response parsing failed: %s", repr(e))
        else:
            is_checking_tm_inv = True
    if is_updating_tm_inv and is_checking_tm_inv:
        try:
            tm_response = requests.get(f"https://tf2.tm/api/InventoryItems?key={authdata.tm_api}")
        except Exception as e:
            log.error("tm check site inv request failed: %s", repr(e))
        if tm_response.text.find('<html') >=0 and tm_response.text.find('Engineering works') >=0:
            log.warn('tm error: Engineering works')
            return
        try:
            tm_response_json = tm_response.json()
        except Exception as e:
            log.error("tm check site inv response parsing failed: %s", repr(e))
        else:
            success_tm = tm_response_json.get("success", "")
            errstr__tm = tm_response_json.get("error", "") or tm_response_json.get("message", "")
            tm_updating_now = tm_response_json.get("updatingNow", False)
            tm_items_in_cache = tm_response_json.get("itemsInCache", 0)
            if success_tm:
                if tm_updating_now == False and tm_items_in_cache > 0:
                    log.info('tm site inventory updated successfully')
                    is_updating_tm_inv = False
                    is_checking_tm_inv = False
                if tm_updating_now == False and tm_items_in_cache == 0:
                    log.info('tm site inventory update finished with fail, will retry later')
                    is_checking_tm_inv = False
                if tm_updating_now == True:
                    log.info('tm site inventory update not finished yet')
            else:
                log.warn("tm check site inv request error: %s", errstr__tm)

def do_trade_tm_sched():
    if is_have_trade_tm:
        do_trade_tm(do_trade_action)

def do_trade_tm(action):
    global is_have_trade_tm, is_updating_tm_inv, tm_errors_count
    if action == 'take' or action == 'give':
        pass 
    else:
        log.error('wrong action')
        return

    if is_have_trade_tm:
        pass
    else:
        return

    if is_updating_tm_inv:
        log.warn('updating tm site inv, skipping trade attempt')
        do_update_tm_inv()
        return

    try:
        tm_response = requests.get(f"https://tf2.tm/api/v2/trade-request-{action}/?key={authdata.tm_api}")
    except Exception as e:
        log.error("tm trade request failed: %s", repr(e))
    if tm_response.text.find('<html') >=0 and tm_response.text.find('Engineering works') >=0:
        log.warn('tm error: Engineering works')
        return
    try:
        tm_response_json = tm_response.json()
    except Exception as e:
        log.error("tm trade response parsing failed: %s", repr(e))
    else:
        success_tm = tm_response_json.get("success", "")
        errstr__tm = tm_response_json.get("error", "") or tm_response_json.get("message", "")
        offer_id   = tm_response_json.get("trade", "")
        if success_tm:
            trade_accepted = False
            while not trade_accepted:
                try:
                    steam_client.accept_trade_offer(offer_id)
                except Exception as e:
                    log.error("error accepting trade offer %s : %s", offer_id, repr(e))
                    if try_amount < 0:
                        log.error("giving up on accepting trade offer %s", offer_id)
                        break
                    log.error("retry to accept trade offer %s (attempt %s/%s)", offer_id, 10-try_amount, try_amount)
                    try_amount -= 1
                else:
                    trade_accepted = True
                    is_have_trade_tm = False
                    tm_errors_count = 0
                    log.info("tm tradeoffer %s accepted", offer_id)
                    is_updating_tm_inv = True
                    log.info('doing update inv after trade')
        else:
            log.warn("tm trade request error: %s", errstr__tm)
            if errstr__tm.find('Мы пытаемся') >= 0 or errstr__tm.find('error: invalid key ') >= 0 or errstr__tm.find('У вас уже есть активные предложения обмена.') >= 0:
                tm_errors_count += 1
                if tm_errors_count >= 5:
                    log.warn('too much tm errors, trying to update inv')
                    is_updating_tm_inv = True

def check_trade_tm():
    global is_have_trade_tm, do_trade_action
    if is_have_trade_tm:
        log.info('already know that we have items to trade')
        return

    try:
        tm_response = requests.get(f"https://tf2.tm/api/v2/items/?key={authdata.tm_api}")
    except Exception as e:
        log.error("tm items request failed: %s", repr(e))
    if tm_response.text.find('<html') >=0 and tm_response.text.find('Engineering works') >=0:
        log.warn('tm error: Engineering works')
        return
    try:
        tm_response_json = tm_response.json()
    except Exception as e:
        log.error("tm items response parsing failed: %s", repr(e))
    else:
        success_tm = tm_response_json.get("success", "")
        errstr__tm = tm_response_json.get("error", "") or tm_response_json.get("message", "")
        if success_tm:
            do_trade_action = ''
            for i in tm_response_json['items']:
                if i['status'] == '2':
                    do_trade_action = 'give'
                    break
                if i['status'] == '4':
                    do_trade_action = 'take'
                    break
            if do_trade_action != '':
                is_have_trade_tm = True
            else:
                log.info('nothing to trade on tm')
        else:
            log.warn("tm items error: %s", errstr__tm)

def start_bot():
    check_trade()
    time.sleep(1)
    ping_tm()
    time.sleep(1)
    check_trade_tm()

    schedule.every(180).seconds.do(check_trade)
    schedule.every(30).minutes.do(session_ok)
    schedule.every(185).seconds.do(ping_tm)
    schedule.every(3).minutes.do(check_trade_tm)
    schedule.every(15).seconds.do(do_trade_tm_sched)
    schedule.every(15).seconds.do(do_update_tm_inv)
    while True:
        schedule.run_pending()
        time.sleep(1)

log.info('started')
log_in_steam()
start_bot()
