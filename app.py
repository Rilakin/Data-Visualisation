import dash
import dash_core_components as dcc
import dash_html_components as html
import dash_table
import hiplot
import pathlib
from json import load
from flask import request
from os import fspath
import plotly.graph_objects as go
import pandas as pd
from dash.dependencies import Input, Output


def shutdown():
    func = request.environ.get("werkzeug.server.shutdown")
    if func is None:
        raise RuntimeError("Not running with the Werkzeug Server")
    func()


def build_trial_dictionary(trial_json_to_build, hyperparameters):
    trial_dict = {}
    trial_dict.update({"trial_id": trial_json_to_build["trial_id"]})

    # get selected hyperparameters
    if hyperparameters:
        for key in hyperparameters:
            value = trial_json_to_build["hyperparameters"]["values"].get(key)
            if value:
                trial_dict.update({key: value})
        trial_dict.update({"score": trial_json_to_build["score"]})

    # get all hyperparameters
    else:
        for key, value in trial_json_to_build["hyperparameters"]["values"].items():
            if key != "tuner/trial_id":
                trial_dict.update({key: value})
        trial_dict.update({"score": trial_json_to_build["score"]})

    return trial_dict


def read_data(**kwargs):
    # get path and search for trials
    hypersearch_directory = kwargs.get("project_dir")
    project_name = kwargs.get("project_name") + "--dense"
    path = pathlib.Path(hypersearch_directory)
    trial_dir = path.joinpath("RESULTS", project_name, kwargs.get("search_dir"))
    trial_path_list = list(trial_dir.glob("**/trial.json"))

    # open trial.json files
    trial_list = list()
    for trial in trial_path_list:
        with open(trial) as trial_json:
            trial_list.append(load(trial_json))

    # read values from trials and write them into a list
    data = list()
    search_parameters = []
    if kwargs.get("search_parameters"):
        for parameter in kwargs.get("search_parameters").split(","):
            search_parameters.append(parameter.strip())

    for trial in trial_list:
        data.append(build_trial_dictionary(trial, search_parameters))

    return data


def create_hiplot_html(**kwargs):
    # create hiplot_graph
    hiplot_experiment = hiplot.Experiment.from_iterable(read_data(**kwargs))
    hiplot_html = hiplot_experiment.to_html()
    return hiplot_html


def create_plotly_plot_list(dataframe):
    dimensions_list = []
    for column in dataframe:
        if dataframe[column].dtype == "object":
            categorized_string_values = dataframe[column].astype("category")
            encoded_string_values = categorized_string_values.cat.codes
            sorted_codes = list(set(encoded_string_values))
            sorted_codes.sort()
            sorted_list = list(set(dataframe[column].values))
            sorted_list.sort()
            dimensions_list.append(
                {"tickvals": sorted_codes,
                 "label": column, "values": encoded_string_values,
                 "ticktext": sorted_list}
            )
        else:
            dimensions_list.append(
                {"label": column, "values": dataframe[column]}
            )
    return dimensions_list


def create_plotly_plot(dataframe):
    graph = go.Figure(data=go.Parcoords(
        line=dict(color=dataframe["score"],
                  colorscale=[[0, "blue"], [0.25, "purple"], [0.5, "red"], [0.75, "orange"], [1, "gold"]]),
        dimensions=create_plotly_plot_list(dataframe)
    )
    )
    graph.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white"
    )
    return graph


def plot(**kwargs):
    hiplot_html = create_hiplot_html(**kwargs)

    # Plotly preparations
    data = read_data(**kwargs)
    dataframe = pd.DataFrame(data)
    plotly_graph = create_plotly_plot(dataframe)

    # App Layout
    app = dash.Dash()
    app.layout = html.Div(children=[
        dcc.RadioItems(
            id="tab_switch",
            options=[
                {"label": "HiPlot", "value": "HiPlot"},
                {"label": "PlotlyPlot", "value": "PlotlyPlot"}
            ],
            value="HiPlot",
            labelStyle={"display": "inline-block"}
        ),
        html.Iframe(id="hiplot", srcDoc=hiplot_html, style={"height": "1200px", "width": "100%"}),
        html.Div(id="dashPlot", children=[
            dcc.Graph(id="parallel_plot", figure=plotly_graph,
                      style={"height": "600px", "width": "100%"}),
            dash_table.DataTable(
                id="datatable",
                columns=[{"name": i, "id": i} for i in dataframe.columns],
                data=dataframe.to_dict("records"),
                filter_action="native",
                sort_action="native",
                sort_mode="multi",
                page_action="native",
                page_current=0,
                page_size=10,
            ),

        ]),
        html.Div(id="container_button_checkbox",
                 children=[
                     html.Button("Close", id="close-hiplot", n_clicks=0, style={"display": "inline-block"}),
                     dcc.Checklist(
                         id="refresh-checkbox",
                         style={"display": "inline-block"},
                         options=[
                             {"label": "Automatic refresh HiPlot (Warning! Refresh deletes interaction)",
                              "value": "refresh"}
                         ]
                     ),
                     dcc.Checklist(
                         id="refresh-checkbox-plotly",
                         style={"display": "none"},
                         options=[
                             {"label": "Automatic refresh Plotly", "value": "refresh"}
                         ]
                     ),
                 ],

                 ),

        html.Div(id="container-button-timestamp"),
        dcc.Interval(
            id="interval-component",
            interval=60000,  # in milliseconds
            n_intervals=0
        )
    ])

    # App Callbacks
    @app.callback(Output("container-button-timestamp", "children"),
                  Input("close-hiplot", "n_clicks"))
    def close_dashboard(btn1):
        changed_id = [p["prop_id"] for p in dash.callback_context.triggered][0]
        if "close-hiplot" in changed_id:
            #shutdown()
            return

    @app.callback(Output("hiplot", "hidden"),
                  Output("refresh-checkbox", "style"),
                  Input("tab_switch", "value"))
    def display_hiplot(content_to_show):
        if content_to_show == "HiPlot":
            return False, {"display": "inline-block"}
        else:
            return True, {"display": "none"}


    @app.callback(Output("dashPlot", "hidden"),
                  Output("refresh-checkbox-plotly", "style"),
                  Input("tab_switch", "value"))
    def display_plotly(content_to_show):
        if content_to_show == "PlotlyPlot":
            return False, {"display": "inline-block"}
        else:
            return True, {'display': 'none'}

    @app.callback(Output("hiplot", "srcDoc"),
                  Input("interval-component", "n_intervals"),
                  Input("refresh-checkbox", "value"))
    def refresh_hiplot(n_intervals, refresh_value):
        if refresh_value:
            return create_hiplot_html(**kwargs)
        else:
            return dash.no_update

    @app.callback(Output("datatable", "data"),
                  Input("interval-component", "n_intervals"),
                  Input("refresh-checkbox-plotly", "value"))
    def refresh_plotly(n_intervals, value):
        if value:
            new_data = read_data(**kwargs)
            new_dataframe = pd.DataFrame(new_data)
            return new_dataframe.to_dict("records")
        else:
            return dash.no_update

    @app.callback(Output("parallel_plot", "figure"),
                  Input("datatable", "derived_virtual_data"))
    def filter_parallelcoords(rows):
        new_dataframe = dataframe if rows is None else pd.DataFrame(rows)
        new_figure = create_plotly_plot(new_dataframe)
        new_figure.update_layout(uirevision="constant")
        return new_figure

    return app


if __name__ == "__main__":
    url = "127.0.0.1:5000"
    assert ":" in url, 'Url must be formatted like: "host:port".'
    host, port = url.split(":")
    app = plot(
        **{"project_name": "test", "project_dir": "F:\TestSample\Viscoelasticity", "search_dir": "hyperband_search_00",
         "search_parameters": "num_layers,activation,units,learning_rate"})
    app.run_server(debug=False, host=host, port=port)
