"""
Tools for the spatial analysis of neighborhood change
"""

import copy
import numpy as np
import pandas as pd
from libpysal.weights import attach_islands
from libpysal.weights.contiguity import Queen, Rook
from libpysal.weights.distance import KNN

from .cluster import (affinity_propagation, gaussian_mixture, kmeans, max_p,
                      skater, spectral, spenc, ward, ward_spatial)


def cluster(dataset,
            n_clusters=6,
            method=None,
            best_model=False,
            columns=None,
            verbose=False,
            **kwargs):
    """
    Create a geodemographic typology by running a cluster analysis on the
    metro area's neighborhood attributes

     Parameters
    ----------
    n_clusters : int
        the number of clusters to derive
    method : str
        the clustering algorithm used to identify neighborhood types
    columns : list-like
        subset of columns on which to apply the clustering

    Returns
    -------
    DataFrame
    """
    assert columns, "You must provide a subset of columns as input"
    assert method, "You must choose a clustering algorithm to use"
    dataset = copy.deepcopy(dataset)
    allcols = columns + ["year"]
    dataset.data = dataset.data.dropna(how='any', subset=columns)
    opset = copy.deepcopy(dataset)
    opset.data = opset.data[allcols]
    opset.data[columns] = opset.data.groupby("year")[columns].apply(
        lambda x: (x - x.mean()) / x.std(ddof=0))
    # option to autoscale the data w/ mix-max or zscore?
    specification = {
        "ward": ward,
        "kmeans": kmeans,
        "ap": affinity_propagation,
        "gm": gaussian_mixture,
        "spectral": spectral,
    }
    model = specification[method](
        opset.data[columns],
        n_clusters=n_clusters,
        best_model=best_model,
        verbose=verbose,
        **kwargs)
    labels = model.labels_.astype(str)
    clusters = pd.DataFrame({
        method: labels,
        "year": dataset.data.year.astype(str),
        "geoid": dataset.data.index
    })
    clusters["key"] = clusters.geoid + clusters.year
    clusters = clusters.drop(columns="year")
    geoid = dataset.data.index.copy()
    dataset.data["key"] = dataset.data.index + dataset.data.year.astype(str)
    dataset.data = dataset.data.merge(clusters, on="key", how="left")
    dataset.data["geoid"] = geoid
    dataset.data.drop(columns='key', inplace=True)
    dataset.data.set_index("geoid", inplace=True)
    return dataset


def cluster_spatial(dataset,
                    n_clusters=6,
                    weights_type="rook",
                    method=None,
                    best_model=False,
                    columns=None,
                    threshold_variable='count',
                    threshold=10,
                    **kwargs):
    """

    Create a *spatial* geodemographic typology by running a cluster
    analysis on the metro area's neighborhood attributes and including a
    contiguity constraint.

    Parameters
    ----------
    n_clusters : int
        the number of clusters to derive
    weights_type : str 'queen' or 'rook'
        spatial weights matrix specification
    method : str
        the clustering algorithm used to identify neighborhood types
    columns : list-like
        subset of columns on which to apply the clustering

    Returns
    -------
    DataFrame

    """
    assert columns, "You must provide a subset of columns as input"
    assert method, "You must choose a clustering algorithm to use"
    dataset = copy.deepcopy(dataset)

    if threshold_variable == "count":
        allcols = columns + ["year"]
        data = dataset.data[allcols].copy()
        data = data.dropna(how="any")
        data[columns] = data.groupby("year")[columns].apply(
            lambda x: (x - x.mean()) / x.std(ddof=0))

    elif threshold_variable is not None:
        threshold_var = data[threshold_variable]
        allcols = list(columns).remove(threshold_variable) + ["year"]
        data = dataset.data[allcols].copy()
        data = data.dropna(how="any")
        data[columns] = data.groupby("year")[columns].apply(
            lambda x: (x - x.mean()) / x.std(ddof=0))

    else:
        allcols = columns + ["year"]
        data = dataset.data[allcols].copy()
        data = data.dropna(how="any")
        data[columns] = data.groupby("year")[columns].apply(
            lambda x: (x - x.mean()) / x.std(ddof=0))

    tracts = dataset.tracts

    def _build_data(data, tracts, year, weights_type):
        df = data.loc[data.year == year].copy().dropna(how="any")
        tracts = tracts.loc[tracts.geoid.isin(df.index)].copy()
        weights = {"queen": Queen, "rook": Rook}
        w = weights[weights_type].from_dataframe(tracts, idVariable="geoid")
        # drop islands from dataset and rebuild weights
        #df.drop(index=w.islands, inplace=True)
        #tracts.drop(index=w.islands, inplace=True)
        #w = weights[weights_type].from_dataframe(tracts, idVariable="geoid")
        knnw = KNN.from_dataframe(tracts, k=1, ids=tracts.geoid.tolist())

        return df, w, knnw

    years = [1980, 1990, 2000, 2010]
    annual = []
    for year in years:
        df, w, knnw = _build_data(data, tracts, year, weights_type)
        annual.append([df, w, knnw])

    datasets = dict(zip(years, annual))

    specification = {
        "spenc": spenc,
        "ward_spatial": ward_spatial,
        "skater": skater,
        "max_p": max_p,
    }

    clusters = []
    for _, val in datasets.items():
        if threshold_variable == "count":
            threshold_var = np.ones(len(val[0]))
            val[1] = attach_islands(val[1], val[2])

        elif threshold_variable is not None:
            threshold_var = threshold_var[threshold.index.isin(
                val[0].index)].values
            try:
                val[1] = attach_islands(val[1], val[2])
            except:
                pass
        else:
            threshold_var = None
        model = specification[method](
            val[0].drop(columns="year"),
            w=val[1],
            n_clusters=n_clusters,
            threshold_variable=threshold_var,
            threshold=threshold,
            **kwargs)
        labels = model.labels_.astype(str)
        labels = pd.DataFrame({
            method: labels,
            "year": val[0].year,
            "geoid": val[0].index
        })
        clusters.append(labels)

    clusters = pd.concat(clusters)
    clusters.set_index("geoid")
    clusters["joinkey"] = clusters.geoid + clusters.year.astype(str)
    clusters = clusters.drop(columns="year")
    geoid = dataset.data.index
    dataset.data[
        "joinkey"] = dataset.data.index + dataset.data.year.astype(str)
    if method in dataset.data.columns:
        dataset.data.drop(columns=method, inplace=True)
    dataset.data = dataset.data.merge(clusters, on="joinkey", how="left")
    dataset.data["geoid"] = geoid
    dataset.data.set_index("geoid", inplace=True)

    return dataset