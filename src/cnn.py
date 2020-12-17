"""
CNN model to predict covid cases 

STATS: (Number of trials = 75)

--> Error (MASE):   

As we are using MASE with CNN and a naive model, the maximum possible error can be fixed (current error cap = 1 (but not strict))

# TODO : Reduce the average MASE with the CNN  (needs fine tuning weekly)

Countries: (MASE in the order confirmed,deaths,recovered)
{
    1.India -> [0.3, 0.78, 0.32]
    2.US -> [0.37, 0.56, 0.5]
    3.Italy -> [1.8, 0.29, 2.76]
    4.Australia -> [3.4, 1, 2.87]
    5.Tanzania -> [1, 1, 1]
    6.Japan -> [2.1, 1.28, 4.01]
    7.China -> [5.34, 1, 1.38]
    8.Canada -> [0.43, 0.38, 2.82]
    9.Brazil -> [2.04, 1.63, 3.95]
    10.Botswana -> [1, 1, 1]
}

--> Runtime:
Avg time taken -> 94.79 seconds
Least time -> 71.88 seconds
Highest time -> 106.63 seconds


--> Downward Cumulative Cases : N/A
- observed in 0/75 trials 

"""
# %%
import pandas as pd

import numpy as np
from collections import Counter

from TSErrors import FindErrors

from sklearn.model_selection import ParameterGrid

from keras.models import Sequential
from keras.layers.convolutional import Conv1D, MaxPooling1D
from keras.layers import Dense, Flatten

import plotly.graph_objects as go
import plotly.io as pio

# module required to get confirmed_global, deaths_global, recovered_global
import app_vars as av
import main

pio.templates.default = "plotly_dark"


# %%
def get_data():

    confirmed_global, deaths_global, recovered_global = (
        av.confirmed_global,
        av.deaths_global,
        av.recovered_global,
    )
    try:
        recovered = recovered_global.groupby("country").sum().T
        deaths = deaths_global.groupby("country").sum().T
        confirmed = confirmed_global.groupby("country").sum().T
    except:
        confirmed_global, deaths_global, recovered_global, _ = main.collect_data()
        recovered = recovered_global.groupby("country").sum().T
        deaths = deaths_global.groupby("country").sum().T
        confirmed = confirmed_global.groupby("country").sum().T

    deaths.index = pd.to_datetime(deaths.index, infer_datetime_format=True)
    recovered.index = pd.to_datetime(
        recovered.index, infer_datetime_format=True)
    confirmed.index = pd.to_datetime(
        confirmed.index, infer_datetime_format=True)

    return deaths, recovered, confirmed


# %%
def create_data_frame(dataframe, country):

    deaths, recovered, confirmed = get_data()

    if dataframe == "deaths":
        data = pd.DataFrame(
            index=deaths.index, data=deaths[country].values, columns=["Total"]
        )

    elif dataframe == "recovered":
        data = pd.DataFrame(
            index=recovered.index, data=recovered[country].values, columns=[
                "Total"]
        )

    elif dataframe == "confirmed":
        data = pd.DataFrame(
            index=confirmed.index, data=confirmed[country].values, columns=[
                "Total"]
        )

    data = data[(data != 0).all(1)]

    data_diff = data.diff()

    # removing the first value from data_diff as it had no previous value and is a NaN after diffrencing
    data_diff = data_diff[1:]

    return data, data_diff


# %%
def make_series(df_name, country, steps):

    data, data_diff = create_data_frame(df_name, country)

    # Taking the values from data_diff and making them an array
    series = np.array(data_diff["Total"])

    X, y = [], []
    for i in range(len(series)):
        end = i + steps
        if end > len(series) - 1:
            break
        x_sample, y_sample = series[i:end], series[end]
        X.append(x_sample)
        y.append(y_sample)

    return data, data_diff, np.array(X), np.array(y)


# %%
def mase(y_true, y_pred):
    er = FindErrors(y_true, y_pred)
    return er.mase()


# %%
def create_param_grid():

    param_grid = {
        "filters": (60, 70),
        "nodes": (60, 70),
        "epochs": (60, 70),
        "activation1": ("swish", "relu", "tanh"),
        "activation2": ("swish", "relu", "tanh"),
    }
    grid = ParameterGrid(param_grid)

    return grid


# %%


def compile_model(p):

    model = Sequential()
    model.add(
        Conv1D(
            filters=p["filters"],
            kernel_size=2,
            activation=p["activation1"],
            input_shape=(14, 1),
        )
    )
    model.add(MaxPooling1D(pool_size=2))
    model.add(Flatten())
    model.add(Dense(p["nodes"], activation=p["activation2"]))
    model.add(Dense(1))
    model.compile(optimizer="adam", loss="mse")

    return model


# %%
def hyperparameter_tuning(grid, X_train, y_train):

    parameters = pd.DataFrame(columns=["MASE", "Parameters"])
    for p in grid:
        model = compile_model(p)

        # reshaping the set to suit the required input shape
        X_train = X_train.reshape((X_train.shape[0], X_train.shape[1], 1))

        model.fit(X_train, y_train, epochs=p["epochs"], verbose=0)
        predictions = model.predict(X_train, verbose=0)

        # flattening the predictions to a 1D array to calculate the MASE
        predictions = predictions.flatten()

        MASE = mase(y_train, predictions)
        parameters = parameters.append(
            {"MASE": MASE, "Parameters": p}, ignore_index=True
        )

    return parameters


# %%
def get_best_params(parameters):

    # sort the dataframe based on MASE values
    final = parameters.sort_values("MASE").reset_index().iloc[0]

    return final.values[2]


# %%
def test_model(p, X_train, X_test, y_train, y_test, data):

    model = compile_model(p)

    # reshaping the set to suit the required input shape
    X_train = X_train.reshape((X_train.shape[0], X_train.shape[1], 1))

    model.fit(X_train, y_train, epochs=p["epochs"], verbose=0)

    # reshaping the set to suit the required input shape
    X_test = X_test.reshape((X_test.shape[0], X_test.shape[1], 1))

    # predicting results of X_test
    predictions = model.predict(X_test, verbose=0)
    predictions = predictions.flatten()

    # Taking the cumulative of the predictions step wise
    # Start is the value just before the test_set, which is used to begin taking the cumulative
    start = data["Total"][-len(y_test) - 1]
    predictions_cumulative = []
    for i in predictions:
        start = start + i
        predictions_cumulative.append(start)

    # The actual cumulative values
    y_test_cumulative = data["Total"][-len(y_test):]

    MASE = mase(y_test_cumulative, predictions_cumulative)

    return MASE


# %%
def make_final_model(p, X, y):
    model = compile_model(p)

    # reshaping the set to suit the required input shape
    X = X.reshape((X.shape[0], X.shape[1], 1))

    model.fit(X, y, epochs=p["epochs"], verbose=0)

    return model


# %%
def forecast(data_diff, data, n, model):

    forecast = []

    for i in range(n):
        l = len(forecast)
        inp = (list(data_diff["Total"][-(n - l):])) + forecast
        inp = np.array(inp)
        inp = inp.reshape(1, 14, 1)
        future = model.predict(inp, verbose=0)
        forecast.append(list(future.flatten())[0])

    forecast_cumulative = []
    start = data["Total"][-1]
    for i in forecast:
        start = start + i
        forecast_cumulative.append(start)

    return forecast_cumulative


# %%
def plot_graph(data, pred):

    datelist = pd.date_range(data.index[-1], periods=15).tolist()
    datelist = datelist[1:]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=data.index, y=data["Total"],
                   mode="lines", name="Up till now")
    )
    fig.add_trace(go.Scatter(x=datelist, y=pred,
                             mode="lines", name="Predictions*"))
    fig.update_layout(template="plotly_dark")

    return fig


# %%


def naive_forecast(study, country):
    df, _ = create_data_frame(study, country)
    datelist = pd.date_range(df.index[-1], periods=15).tolist()[1:]
    predictions = [df.Total[-1]] * 14
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=df.index, y=df["Total"], mode="lines", name="Up till now")
    )
    fig.add_trace(
        go.Scatter(x=datelist, y=predictions,
                   mode="lines", name="Predictions*")
    )
    fig.update_layout(template="plotly_dark")
    return 1, fig, predictions


# %%

def check_slope(x, y):
    c = Counter(np.diff(y) / np.diff(x))
    return 0 not in [i[0] for i in c.most_common(1)]


def cnn_predict(df_name, country):

    data, data_diff, X, y = make_series(df_name, country, 14)
    grid = create_param_grid()
    n = len(data_diff) * 17 // 20
    X_train, X_test, y_train, y_test = X[:n], X[n:], y[:n], y[n:]
    parameters = hyperparameter_tuning(grid, X_train, y_train)
    p = get_best_params(parameters)
    MASE = (test_model(p, X_train, X_test, y_train, y_test, data)).round(2)
    if MASE <= 1 or check_slope([1, 2, 3, 4, 5], data.Total[-5:]):
        cnn = make_final_model(p, X, y)
        f = forecast(data_diff, data, 14, cnn)
        f = list(map(int, f))
        fig = plot_graph(data, f)
    else:
        MASE, fig, f = naive_forecast(df_name, country)

    datelist = pd.date_range(data.index[-1], periods=8).tolist()[1:]
    predictions = pd.DataFrame(
        data={"Date": list(map(lambda x: x.strftime('%d.%m.%Y'), datelist)), "Cases": f[:7]})

    return fig, MASE, predictions


"""
# EXAMPLE
fig, MASE, predictions = cnn_predict("confirmed","India")
"""
