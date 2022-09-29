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
        elif success_steamtrader == False and errcode_steamtrader:
            log.warn("Steam-trader exchange error: %s (%s)", errstr__steamtrader, errcode_steamtrader)
        else:
            log.warn('wut?')

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

def start_bot():
    check_trade()

    schedule.every(180).seconds.do(check_trade)
    schedule.every(30).minutes.do(session_ok)

    while True:
        schedule.run_pending()
        time.sleep(1)

log.info('started')
log_in_steam()
start_bot()
