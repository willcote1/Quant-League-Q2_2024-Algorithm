from AlgorithmImports import *
import numpy as np
from collections import deque
from datetime import timedelta

class MultiAssetPortfolioOptimization(QCAlgorithm):

    def Initialize(self):
        # 1) Backtest window & capital
        self.SetStartDate(2016, 1, 1)
        self.SetEndDate(2025, 1, 1)
        self.INIT_CASH = 1000000
        self.SetCash(self.INIT_CASH)  # Fixed: changed set_cash to SetCash

        # Initialization for the Buy and Hold Benchmark
        self.buy_and_hold_initialized = False
        self.buy_and_hold_shares = 0
        
        # 2) Set brokerage/benchmark
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
        self.SetBenchmark("SPY")
        
        # 3) Primary leveraged ETFs (2× leveraged, from different sectors)
        # SSO is now included as a sector rather than a rotation ETF.
        self.longAssets = {
            "TECH": self.AddEquity("QLD", Resolution.Daily).Symbol,    # Technology (Nasdaq-100)
            "ENERGY": self.AddEquity("ERX", Resolution.Daily).Symbol,    # Energy
            "IND": self.AddEquity("DNI", Resolution.Daily).Symbol,       # Industrials
            "SSO": self.AddEquity("SSO", Resolution.Daily).Symbol         # S&P 500 as a sector
        }
        
        # 4) Rotation hedge asset: TBF.
        self.tbfSymbol = self.AddEquity("TBF", Resolution.Daily).Symbol
        
        # 5) Define a candidate universe for the bond portfolio.
        self.bondCandidates = {
            "BIL": self.AddEquity("BIL", Resolution.Daily).Symbol,
            "SHY": self.AddEquity("SHY", Resolution.Daily).Symbol,
            "HYG": self.AddEquity("HYG", Resolution.Daily).Symbol
        }
        # For the TBF hedge, we assume a fixed duration.
        self.durationTBF = -17
        
        # 6) Additional assets for the valuation indicator:
        # SPY to extract forward earnings yield.
        self.spySymbol = self.AddEquity("SPY", Resolution.Daily).Symbol
        # TNX as a proxy for the 10-year Treasury yield.
        self.tenYearSymbol = self.AddEquity("TNX", Resolution.Daily).Symbol
        # When the valuation indicator triggers, invest in 2× leveraged gold.
        self.goldSymbol = self.AddEquity("UGLD", Resolution.Daily).Symbol
        
        # 7) Indicators for individual signals:
        # 20-day moving average for each leveraged ETF.
        self.momentumMA = {}
        for symbol in self.longAssets.values():
            self.momentumMA[symbol] = self.SMA(symbol, 20, Resolution.Daily)
        # 20-day volume SMA for leveraged ETFs.
        self.volumeSMA = {}
        self.volumeMultiplierThreshold = 1.5
        for symbol in self.longAssets.values():
            self.volumeSMA[symbol] = self.SMA(symbol, 20, Resolution.Daily, Field.Volume)
        
        # SPY indicator for valuation:
        self.spyMA = self.SMA(self.spySymbol, 20, Resolution.Daily)
        
        # 8) Warm up so that all indicators are ready.
        self.SetWarmUp(200)
        
        # 9) Stop loss and take profit parameters.
        self.StopLossPctEquity = 0.04
        self.TakeProfitPctEquity = 0.2
        
        # 10) Data structures for tracking orders.
        self.ordersDict = {}
        self.entryPrices = {}
        
        # -------------------------------------------------------------------
        # Setup for inverse-vol weighting among leveraged ETFs.
        # -------------------------------------------------------------------
        self.volPeriod = 20  # rolling window for daily returns
        self.priceHistory = {}
        self.previousCloses = {}
        for symbol in self.longAssets.values():
            self.InitializeDailyReturnTracking(symbol)
        
        self.Debug("Initialization Complete")
    
    
    # --------------------- DAILY RETURN TRACKING ----------------------------
    def InitializeDailyReturnTracking(self, symbol):
        self.priceHistory[symbol] = deque(maxlen=self.volPeriod)
        self.previousCloses[symbol] = 0
        consolidator = TradeBarConsolidator(timedelta(days=1))
        consolidator.DataConsolidated += lambda sender, bar: self.OnDailyBarConsolidated(bar, symbol)
        self.SubscriptionManager.AddConsolidator(symbol, consolidator)
    
    def OnDailyBarConsolidated(self, bar, symbol):
        prev_close = self.previousCloses[symbol]
        if prev_close != 0:
            daily_return = (bar.Close - prev_close) / prev_close
            self.priceHistory[symbol].append(daily_return)
        self.previousCloses[symbol] = bar.Close
    
    
    # --------------------- FUNDAMENTAL INDICATORS ----------------------------
    def GetForwardEarningsYield(self):
        """
        Retrieve the S&P 500 forward earnings yield using SPY's fundamental data.
        This example attempts to use CompanyReference.ForwardEarningsYield.
        """
        fundamentals = self.Securities[self.spySymbol].Fundamentals
        if fundamentals is not None and fundamentals.CompanyReference is not None:
            if hasattr(fundamentals.CompanyReference, "ForwardEarningsYield"):
                return fundamentals.CompanyReference.ForwardEarningsYield
        return None
    
    
    def Get10YearYield(self):
        """
        Retrieve the 10-year Treasury yield from the TNX asset.
        Assumes TNX price is in percentage points (e.g., 3.5 for 3.5%),
        converting it to a decimal.
        """
        if self.tenYearSymbol in self.Securities:
            price = self.Securities[self.tenYearSymbol].Price
            if price is not None:
                return price / 100.0
        return None
    
    
    # --------------------- MAIN TRADING LOGIC -------------------------------
    def OnData(self, data):
        if self.IsWarmingUp:
            return

        if not self.buy_and_hold_initialized:
            # Fixed: access Securities[spySymbol] instead of securities[self.symbol]
            self.buy_and_hold_shares = self.INIT_CASH / self.Securities[self.spySymbol].Price
            self.Log("Bought " + str(self.buy_and_hold_shares) + " shares")
            self.buy_and_hold_initialized = True

        self.UpdatePlot()
        
        # --- Valuation Indicator: Compare S&P 500 forward earnings yield and 10-year yield.
        forwardEY = self.GetForwardEarningsYield()
        tenYearYield = self.Get10YearYield()
        if forwardEY is not None and tenYearYield is not None:
            # Theory: if the forward earnings yield is lower than the 10-year yield,
            # stocks are overvalued. In that case, liquidate positions and invest in 2× gold.
            if forwardEY < tenYearYield:
                assetsToClear = list(self.longAssets.values()) + [self.tbfSymbol] + list(self.bondCandidates.values())
                for sym in assetsToClear:
                    if self.Portfolio[sym].Invested:
                        self.Liquidate(sym)
                if not self.Portfolio[self.goldSymbol].Invested:
                    self.SetHoldings(self.goldSymbol, 1.0)
                    self.Debug("Valuation indicator triggered: Forward earnings yield < 10-year yield. Investing in 2× Gold (UGLD).")
                return  # Exit OnData after switching to gold.
            else:
                # If not triggered, ensure any gold position is liquidated.
                if self.Portfolio[self.goldSymbol].Invested:
                    self.Liquidate(self.goldSymbol)
        
        # --- Next, evaluate individual leveraged ETF signals (long signals).
        bullishSymbols = []
        for symbol in self.longAssets.values():
            if symbol not in data or data[symbol] is None:
                continue
            price = data[symbol].Price
            if self.momentumMA[symbol].IsReady and self.volumeSMA[symbol].IsReady:
                if price > self.momentumMA[symbol].Current.Value:
                    bullishSymbols.append(symbol)
                else:
                    if self.Portfolio[symbol].Invested:
                        self.Liquidate(symbol)
                        self.CancelOrdersForSymbol(symbol)
            else:
                continue
        
        if bullishSymbols:
            # Liquidate rotation and bond positions.
            for sym in [self.tbfSymbol] + list(self.bondCandidates.values()):
                if self.Portfolio[sym].Invested:
                    self.Liquidate(sym)
            
            # Allocate 100% among the bullish signals using inverse volatility weighting.
            inv_vol_bullish = {}
            total_inv_vol_bullish = 0.0
            for symbol in bullishSymbols:
                returns = list(self.priceHistory[symbol])
                vol = np.std(returns, ddof=1) if len(returns) > 1 else 0.02
                if vol <= 0:
                    vol = 1e-6
                inv_vol = 1.0 / vol
                inv_vol_bullish[symbol] = inv_vol
                total_inv_vol_bullish += inv_vol
            
            for symbol in bullishSymbols:
                weight = inv_vol_bullish[symbol] / total_inv_vol_bullish
                self.SetHoldings(symbol, weight)
                if self.Portfolio[symbol].Invested and symbol not in self.ordersDict:
                    entryPrice = data[symbol].Price
                    self.entryPrices[symbol] = entryPrice
                    self.PlaceStopAndTakeProfit(symbol, entryPrice, True,
                                                self.StopLossPctEquity,
                                                self.TakeProfitPctEquity)
        else:
            # No bullish signals: use bond rotation strategy.
            self.RotateRotation(data)
    
    
    # --------------------- ROTATION LOGIC (BOND Rotation Only) -------------------------------
    def RotateRotation(self, data):
        """
        When no individual signals are present, use bond rotation strategy.
        """
        # Liquidate any positions in long sector assets.
        for symbol in self.longAssets.values():
            if self.Portfolio[symbol].Invested:
                self.Liquidate(symbol)
                self.CancelOrdersForSymbol(symbol)
        
        # Liquidate TBF if invested.
        if self.Portfolio[self.tbfSymbol].Invested:
            self.Liquidate(self.tbfSymbol)
        
        bondSymbol = self.SelectBond()
        if bondSymbol is None:
            return
        
        # Retrieve real bond duration from fundamentals.
        bondDuration = self.GetBondDuration(bondSymbol)
        if bondDuration is None or bondDuration <= self.durationTBF:
            self.Debug(f"Unable to get valid duration for {bondSymbol.Value}")
            return
        
        # Compute immunization weights:
        # w_bond * bondDuration + w_TBF * durationTBF = 0, with w_bond + w_TBF = 1.
        w_bond = -self.durationTBF / (bondDuration - self.durationTBF)
        w_tbf = bondDuration / (bondDuration - self.durationTBF)
        
        # Liquidate any bond positions not selected.
        for bond in self.bondCandidates.values():
            if bond != bondSymbol and self.Portfolio[bond].Invested:
                self.Liquidate(bond)
        
        self.SetHoldings(bondSymbol, w_bond)
        self.SetHoldings(self.tbfSymbol, w_tbf)
        self.Debug(f"Bond rotation: Selected {bondSymbol.Value} with duration {bondDuration:0.2f} years - Weights: Bond={w_bond:0.2%}, TBF={w_tbf:0.2%}")
    
    
    def SelectBond(self):
        """Select the bond ETF with the maximum yield using real fundamental data."""
        bestYield = -999
        bestBond = None
        for key, symbol in self.bondCandidates.items():
            bondYield = self.GetBondYield(symbol)
            if bondYield is not None and bondYield > bestYield:
                bestYield = bondYield
                bestBond = symbol
        return bestBond
    
    
    def GetBondYield(self, symbol):
        """Return the bond yield using real fundamental data from CompanyReference.
           Here we check for a DividendYield attribute as a proxy for yield."""
        fundamentals = self.Securities[symbol].Fundamentals
        if fundamentals is not None and fundamentals.CompanyReference is not None:
            if hasattr(fundamentals.CompanyReference, "DividendYield"):
                return fundamentals.CompanyReference.DividendYield
        return None
    
    
    def GetBondDuration(self, symbol):
        """Return the bond duration using real fundamental data from CompanyReference."""
        fundamentals = self.Securities[symbol].Fundamentals
        if fundamentals is not None and fundamentals.CompanyReference is not None:
            if hasattr(fundamentals.CompanyReference, "Duration"):
                return fundamentals.CompanyReference.Duration
        return None
    
    
    # ----------------- ORDER MANAGEMENT (STOP LOSS & TAKE PROFIT) -----------------------
    def PlaceStopAndTakeProfit(self, symbol, entryPrice, long, stopPct, tpPct):
        self.CancelOrdersForSymbol(symbol)
        if long:
            stopPrice = entryPrice * (1 - stopPct)
            tpPrice   = entryPrice * (1 + tpPct)
        else:
            stopPrice = entryPrice * (1 + stopPct)
            tpPrice   = entryPrice * (1 - tpPct)
        quantity = self.Portfolio[symbol].Quantity
        closeQty = -quantity
        stopTicket = self.StopMarketOrder(symbol, closeQty, stopPrice)
        tpTicket   = self.LimitOrder(symbol, closeQty, tpPrice)
        self.ordersDict[symbol] = {"stop": stopTicket, "tp": tpTicket}
        self.Debug(f"{symbol.Value}: Entry={entryPrice:.2f}, Stop={stopPrice:.2f}, TP={tpPrice:.2f}")
    
    def CancelOrdersForSymbol(self, symbol):
        if symbol in self.ordersDict:
            orders = self.ordersDict[symbol]
            if orders["stop"] is not None:
                self.Transactions.CancelOrder(orders["stop"].OrderId)
            if orders["tp"] is not None:
                self.Transactions.CancelOrder(orders["tp"].OrderId)
            del self.ordersDict[symbol]
    
    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status == OrderStatus.Filled:
            for sym, orders in list(self.ordersDict.items()):
                if orderEvent.OrderId in [orders["stop"].OrderId, orders["tp"].OrderId]:
                    self.CancelOrdersForSymbol(sym)
                    self.Debug(f"Exit order filled for {sym.Value}, cancelled the other order.")


    def UpdatePlot(self):
        # Updating the Performance chart
        
        # Plot the total portfolio value
        self.Plot("Performance", "Total Value", self.Portfolio.TotalPortfolioValue)
        # Plot the benchmark - Fixed: access spySymbol instead of self.symbol
        if self.buy_and_hold_initialized:
            benchmark = self.Securities[self.spySymbol].Price
            self.Plot("Performance", "Buy and Hold", benchmark * self.buy_and_hold_shares)
