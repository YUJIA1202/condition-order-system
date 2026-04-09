from xtquant.xttrader import XtQuantTrader, _XTTYPE_
trader = XtQuantTrader(r"C:\Users\86182\Desktop\etf-desk\国金证券QMT交易端\userdata_mini", 1)
trader.start()
trader.connect()
print(dir(trader))