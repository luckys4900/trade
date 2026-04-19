import json
import pandas as pd
import webbrowser
import os

def generate_dashboard():
    csv_file = 'btc_usdt_4h_unified.csv'
    if not os.path.exists(csv_file):
        print(f"Error: {csv_file} not found.")
        return

    df = pd.read_csv(csv_file)
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    candles = []
    valid_times = set()
    
    for _, row in df.iterrows():
        t = int(row['datetime'].timestamp())
        if t not in valid_times:
            candles.append({
                "time": t,
                "open": row['open'],
                "high": row['high'],
                "low": row['low'],
                "close": row['close']
            })
            valid_times.add(t)

    # Sort candles to be absolutely sure
    candles.sort(key=lambda x: x['time'])

    trades_file = 'backtest_trades_history.json'
    markers = []
    if os.path.exists(trades_file):
        with open(trades_file, 'r') as f:
            trades = json.load(f)
        
        for t in trades:
            t_in = int(pd.to_datetime(t['t_in']).timestamp())
            t_out = int(pd.to_datetime(t['t_out']).timestamp())
            
            is_long = t['side'] == 'LONG'
            is_win = t['pnl'] > 0
            
            if t_in in valid_times:
                markers.append({
                    "time": t_in,
                    "position": "belowBar" if is_long else "aboveBar",
                    "color": "#26a69a" if is_long else "#ef5350",
                    "shape": "arrowUp" if is_long else "arrowDown",
                    "text": f"ENTER {t['side']}"
                })
            if t_out in valid_times:
                markers.append({
                    "time": t_out,
                    "position": "aboveBar" if is_long else "belowBar",
                    "color": "#2196F3" if is_win else "#FF9800",
                    "shape": "circle",
                    "text": f"EXIT {'WIN' if is_win else 'LOSS'}"
                })
            
    markers.sort(key=lambda x: x['time'])
    
    # Remove duplicate markers by time to prevent lightweight-charts from crashing
    unique_markers = []
    seen_marker_times = set()
    for m in markers:
        if m['time'] not in seen_marker_times:
            unique_markers.append(m)
            seen_marker_times.add(m['time'])
        else:
            # If multiple events happen at the same time, combine their text
            for um in unique_markers:
                if um['time'] == m['time']:
                    um['text'] += " & " + m['text']
                    break

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Qwen Unified - Dashboard</title>
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body {{ background-color: #131722; color: #d1d4dc; font-family: 'Trebuchet MS', sans-serif; margin: 0; overflow: hidden; }}
        #chart-container {{ width: 100vw; height: 100vh; position: absolute; top:0; left:0; }}
        .overlay {{ position: absolute; top: 10px; left: 20px; z-index: 10; pointer-events: none; }}
        h1 {{ margin: 0; font-size: 22px; color: #fff; }}
        .stats {{ margin-top: 10px; display: flex; gap: 15px; }}
        .stat-box {{ background: rgba(30,34,45,0.8); padding: 8px 12px; border-radius: 4px; border: 1px solid #2b2b43; }}
        .stat-box span {{ color: #787b86; font-size: 11px; display: block; }}
        .stat-box strong {{ color: #d1d4dc; font-size: 15px; }}
    </style>
</head>
<body>
    <div id="chart-container"></div>
    <div class="overlay">
        <h1>Advanced Backtest Dashboard</h1>
        <div class="stats">
            <div class="stat-box"><span>Candles</span><strong>{len(candles)}</strong></div>
            <div class="stat-box"><span>Trades</span><strong>{len(trades) if os.path.exists(trades_file) else 0}</strong></div>
        </div>
    </div>
    
    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            const chartOptions = {{
                layout: {{ textColor: '#d1d4dc', background: {{ type: 'solid', color: '#131722' }} }},
                grid: {{ vertLines: {{ color: '#2b2b43' }}, horzLines: {{ color: '#2b2b43' }} }},
                crosshair: {{ mode: 0 }}, 
                timeScale: {{ timeVisible: true, secondsVisible: false }}
            }};
            
            const container = document.getElementById('chart-container');
            const chart = LightweightCharts.createChart(container, chartOptions);
            
            const series = chart.addCandlestickSeries({{
                upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
                wickUpColor: '#26a69a', wickDownColor: '#ef5350'
            }});
            
            const data = {json.dumps(candles)};
            series.setData(data);
            
            const markers = {json.dumps(unique_markers)};
            if (markers.length > 0) {{
                series.setMarkers(markers);
            }}
            
            chart.timeScale().fitContent();
            
            window.addEventListener('resize', () => {{
                chart.applyOptions({{ width: window.innerWidth, height: window.innerHeight }});
            }});
        }});
    </script>
</body>
</html>"""

    output_file = 'advanced_dashboard.html'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Dashboard generated at {output_file}")
    
    try:
        # Use PowerShell to invoke default browser reliably
        os.system(f'powershell -Command "Invoke-Item \'{output_file}\'"')
    except:
        pass

if __name__ == "__main__":
    generate_dashboard()