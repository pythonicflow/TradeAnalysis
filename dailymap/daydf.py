import asyncio
import asyncpg
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
import pytz
import plotly.graph_objects as go
import sys
sys.path.append('..')
import config


# Sierra Chart epoch start
sc_epoch = datetime(1899, 12, 30, tzinfo=pytz.UTC)

# Function to convert time stamps to human-readable date/time
def convert_sc_datetime(sc_datetime_ms):
    delta = timedelta(microseconds=sc_datetime_ms)
    actual_datetime = sc_epoch + delta
    local_tz = pytz.timezone('America/Chicago')  # Central Time
    local_datetime = actual_datetime.astimezone(local_tz)
    return local_datetime

# Create a database connection
async def create_db_connection():
    return await asyncpg.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME
    )

# Get the start time of the day
def get_sc_time(date):
    date = datetime.strptime(date, "%Y-%m-%d")
    start_of_day = date.replace(hour=8, minute=30, second=0, microsecond=0, tzinfo=pytz.UTC)
    delta = start_of_day - sc_epoch
    sc_start_of_day = delta.total_seconds() * 1e6  # Convert to microseconds
    return int(sc_start_of_day)

# Fetch data from the database
async def fetch_data(date, min_quantity):
    start_time = get_sc_time(date)
    conn = await create_db_connection()
    rows = await conn.fetch(f'SELECT * FROM public."esm24" WHERE "scdatetime" >= {start_time} AND "quantity" > {min_quantity} ORDER BY "scdatetime" DESC;')
    df = pd.DataFrame(rows, columns=['scdatetime', 'price', 'quantity', 'side'])
    df['scdatetime'] = df['scdatetime'].apply(convert_sc_datetime)
    df['scdatetime_str'] = df['scdatetime'].dt.strftime('%H:%M:%S.%f')
    await conn.close()
    return df

app = dash.Dash(__name__)

# Create the layout of the app with input fields and a graph
app.layout = html.Div([
    html.Label('Date: '),
    dcc.Input(id='date-input', type='text', value='2024-05-10'), # initial date value
    html.Label(' Minimum Quantity: '),
    dcc.Input(id='min-quantity-input', type='number', value=10),  # initial min quantity value
    dcc.Graph(id='live-graph')
])

# Update the graph based on the input values
@app.callback(Output('live-graph', 'figure'),
              [Input('date-input', 'value'), Input('min-quantity-input', 'value')])
def update_graph_live(date, min_quantity):
    df = asyncio.run(fetch_data(date, min_quantity))
    color_map = {0: 'lightcoral', 1: 'lightblue'}

    # Filter the data to only include times between 08:30 and 15:15 (market hours for CME E-mini S&P 500 futures, central time)
    df = df.set_index('scdatetime')
    df = df.between_time('08:30', '15:15')
    df = df.reset_index()

    # Create a scatter plot of the data
    fig = go.Figure()

    # Add markers for buy and sell orders
    for side in [0, 1]:
        df_side = df[df['side'] == side]
        fig.add_trace(go.Scatter(x=df_side['scdatetime'], y=df_side['price'], mode='markers', 
                                marker=dict(size=df_side['quantity'], color=color_map[side]),
                                hovertemplate=
                                '<i>Time</i>: %{customdata}'+
                                '<br><i>Price</i>: %{y}'+
                                '<br><b>Quantity</b>: %{marker.size}<br>',
                                customdata=df_side['scdatetime_str']))

    fig.update_layout(
        template="ggplot2",
        plot_bgcolor='#333333',  # Background color of the plot
        paper_bgcolor='#333333',  # Background color of the paper
        font=dict(family="Courier New, monospace", size=18, color="white"),
        title_font=dict(size=24, family='Verdana, sans-serif', color='lightblue'),
        legend_title_font=dict(family="Times New Roman, Times, serif", size=16, color='lightgreen'),
        xaxis=dict(showgrid=True, gridwidth=1, gridcolor='lightgray'),
        yaxis=dict(showgrid=True, gridwidth=1, gridcolor='lightgray', tickmode = 'linear', tick0 = 0, dtick = 1.00, side='right'),
        hovermode='closest',
        autosize=False,  # Turn off automatic sizing
        width=4200,  # Set the width of the plot
        height=2200  # Set the height of the plot
    )
    
    # Set the x-axis range to be between 08:15 and 15:30
    date = datetime.strptime(date, "%Y-%m-%d")
    start_range = date.replace(hour=8, minute=15).isoformat()
    end_range = date.replace(hour=15, minute=30).isoformat()
    fig.update_xaxes(range=[start_range, end_range])
    # Set the y-axis to a fixed price range
    df_day = df[(df['scdatetime'] >= start_range) & (df['scdatetime'] <= end_range)]

    # Set the y-axis range to be 5 units below the minimum price and 5 units above the maximum price
    min_price = df_day['price'].min() - 5  # 5 units below
    max_price = df_day['price'].max() + 5  # 5 units above
    dtick_value = 1.00  # Set the tick interval for the y-axis

    fig.update_yaxes(range=[min_price, max_price], tickmode='linear', tick0=0, dtick=dtick_value)

    return fig

if __name__ == '__main__':
    app.run_server(debug=True, port=8052)
