# Quant-League-Q2_2025-Algorithm

Link to the live Quant League Competition leaderboard which our strategy competes in: https://www.quantconnect.com/league/

**Investment Thesis for the Multi-Asset Portfolio Optimization Strategy**

1. **Overview and Philosophy**  
   This strategy seeks to balance growth opportunities with downside protection by combining:

   - **Leveraged equity sector ETFs** for capturing market upside in distinct economic sectors and broad market exposure (Nasdaq-100, Energy, Industrials, S&P 500).  
   - **Bond rotation** for periods when equity signals are absent, selecting among different bond ETFs by yield.  
   - **Hedging through duration matching** (using TBF) and a valuation-based overlay that rotates into 2× leveraged gold (UGLD) when the S&P 500 becomes relatively overvalued.  

2. **Asset Universe**  
   - **Leveraged Equity ETFs**  
     - **QLD (2× Nasdaq-100)** 
     - **ERX (2× Energy Sector)**  
     - **DNI (Industrials)** 
     - **SSO (2× S&P 500)** 
   
   - **Defensive & Hedging Positions**  
     - **TBF (Inverse Treasury ETF)**
     - **BIL, SHY, HYG**  

   - **Valuation Hedge & Rotation**  
     - **UGLD (2× Gold)**

3. **Key Signals and Indicators**  
   1. **Momentum & Volume SMA for Leveraged ETFs**  
      - A **20-day moving average** (MA) on price determines momentum. If the ETF’s price is above its MA, it suggests a bullish trend. The strategy invests in that ETF.  
      - If the price moves below its MA, the position is closed.  

   2. **Valuation Overlay (Forward Earnings Yield vs. 10-Year Treasury Yield)**  
      - **Forward Earnings Yield (Fwd EY)** is a proxy for equity market valuation. A lower Fwd EY relative to the 10-year Treasury yield indicates that equities may be overpriced.  
      - If **Fwd EY < 10-year yield**, the strategy exits equity and bond positions, rotating fully into leveraged gold (UGLD). This aims to sidestep overvalued equity markets and capitalize on gold’s safe-haven role.  
      - If **Fwd EY ≥ 10-year yield**, the gold position is liquidated, allowing the strategy’s equity or bond rotation logic to determine investments.

4. **Position Sizing via Inverse Volatility**  
   When multiple equity ETFs generate bullish signals, the strategy allocates capital proportionally to the inverse of each ETF’s historical volatility (using a 20-day rolling window of daily returns). This approach aims to:
   - **Reward lower-volatility assets** by assigning them a higher weight.  
   - **Balance the portfolio** so that no single high-volatility ETF dominates the risk budget.  
   - Potentially **reduce drawdowns** by tilting exposure toward assets that have exhibited more stable recent returns.

5. **Bond Rotation Logic**  
   When no equity signals are bullish, the strategy rotates into a bond position:
   - **Bond Selection by Yield**: Among BIL, SHY, and HYG, the strategy selects the ETF with the highest yield (using fundamental data, e.g., DividendYield as a proxy).  
   - **Immunization with TBF**: Once the bond is chosen, the algorithm calculates a **duration hedge** by pairing it with a short Treasury position via TBF.  
     - The hedge weights ensure the combined duration is near zero, aiming to protect the strategy from interest-rate risk when yields shift.

6. **Risk Management: Stop Loss and Take Profit**  
     - **Stop-loss order** at 4% below entry price.  
     - **Take-profit order** at 20% above entry price.  
