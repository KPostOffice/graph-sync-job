#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# graph-sync-job
# Copyright(C) 2018 Fridolin Pokorny
#
# This program is free software: you can redistribute it and / or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""Graph syncing logic for the Thoth project."""

import os
import logging

import click

from prometheus_client import CollectorRegistry, Gauge, Counter, push_to_gateway

from thoth.common import init_logging
from thoth.common import __version__ as __common__version__
from thoth.storages import __version__ as __storages__version__
from thoth.storages import sync_analysis_documents
from thoth.storages import sync_solver_documents


__version__ = f"0.5.1+storage.{__storages__version__}.common.{__common__version__}"
__author__ = "Christoph Görn <goern@redhat.com>"

init_logging()
_LOGGER = logging.getLogger('thoth.graph_sync_job')

prometheus_registry = CollectorRegistry()

thoth_metrics_exporter_info = Gauge('graph_sync_job_info',
                                    'Thoth Graph Sync Job information', ['version'],
                                    registry=prometheus_registry)
thoth_metrics_exporter_info.labels(__version__).inc()

_METRIC_SECONDS = Gauge(
    'graph_sync_job_runtime_seconds', 'Runtime of graph sync job in seconds.',
    registry=prometheus_registry)

_METRIC_SOLVER_RESULTS_PROCESSED = Counter(
    'graph_sync_solver_results_processed', 'Solver results processed',
    registry=prometheus_registry)
_METRIC_SOLVER_RESULTS_SYNCED = Counter(
    'graph_sync_solver_results_synced', 'Solver results synced',
    registry=prometheus_registry)
_METRIC_SOLVER_RESULTS_SKIPPED = Counter(
    'graph_sync_solver_results_skipped', 'Solver results skipped processing',
    registry=prometheus_registry)
_METRIC_SOLVER_RESULTS_FAILED = Counter(
    'graph_sync_solver_results_failed', 'Solver results failed processing',
    registry=prometheus_registry)

_METRIC_ANALYSIS_RESULTS_PROCESSED = Counter(
    'graph_sync_analysis_results_processed', 'Analysis results processed',
    registry=prometheus_registry)
_METRIC_ANALYSIS_RESULTS_SYNCED = Counter(
    'graph_sync_analysis_results_synced', 'Analysis results synced',
    registry=prometheus_registry)
_METRIC_ANALYSIS_RESULTS_SKIPPED = Counter(
    'graph_sync_analysis_results_skipped', 'Analysis results skipped processing',
    registry=prometheus_registry)
_METRIC_ANALYSIS_RESULTS_FAILED = Counter(
    'graph_sync_analysis_results_failed', 'Analysis results failed processing',
    registry=prometheus_registry)


def _print_version(ctx, _, value):
    """Print package releases version and exit."""
    if not value or ctx.resilient_parsing:
        return
    # Reuse thoth-storages version as we rely on it.
    click.echo(__version__)
    ctx.exit()


@click.command()
@click.option('--version', is_flag=True, is_eager=True, callback=_print_version, expose_value=False,
              help="Print version and exit.")
@click.option('--graph-hosts', type=str, default=[GraphDatabase.DEFAULT_HOST],
              show_default=True, metavar=GraphDatabase.ENVVAR_HOST_NAME,
              envvar=GraphDatabase.ENVVAR_HOST_NAME, multiple=True,
              help="Hostname to the graph instance to perform sync to.")
@click.option('--graph-port', type=int, default=GraphDatabase.DEFAULT_PORT, show_default=True, metavar='HOST',
              envvar=GraphDatabase.ENVVAR_HOST_PORT,
              help="Port number to the graph instance to perform sync to.")
@click.option('--solver-results-store-host', type=str, show_default=True, metavar='HOST', default=None,
              help="Hostname to solver results store from which the sync should be performed.")
@click.option('--analysis-results-store-host', type=str, show_default=True, metavar='HOST', default=None,
              help="Hostname to analysis results store from which the sync should be performed.")
@click.option('-v', '--verbose', is_flag=True, envvar='THOTH_GRAPH_SYNC_DEBUG',
              help="Be more verbose about what's going on.")
@click.option('--force-solver-results-sync', is_flag=True, envvar='THOTH_GRAPH_SYNC_FORCE_SOLVER_RESULTS_SYNC',
              help="Force sync of solver results regardless if they exist (duplicate entries will not be created).")
@click.option('--force-analysis-results-sync', is_flag=True, envvar='THOTH_GRAPH_SYNC_FORCE_ANALYSIS_RESULTS_SYNC',
              help="Force sync of solver results regardless if they exist (duplicate entries will not be created).")
@click.option('--metrics-pushgateway-url', type=str, default='pushgateway:80', show_default=True,
              envvar='THOTH_METRICS_PUSHGATEWAY_URL',
              help="Send job metrics to a Prometheus pushgateway URL.")
def cli(verbose, solver_results_store_host, analysis_results_store_host, graph_hosts, graph_port,
        force_solver_results_sync, force_analysis_results_sync, metrics_pushgateway_url):
    """Sync analyses and solver results to the graph database."""
    logging.getLogger('thoth').setLevel(
        logging.DEBUG if verbose else logging.INFO)
    _LOGGER.debug('Debug mode is on')

    _THOTH_METRICS_PUSHGATEWAY_URL = os.getenv('THOTH_METRICS_PUSHGATEWAY_URL')

    if not only_one_kind and document_ids:
        _LOGGER.error(
            "Explicitly specified documents to be synced can be specified only with one of the --only-* options"
        )
        return 2

    with _METRIC_SECONDS.time():
        if not only_one_kind or only_solver_documents:
            _METRIC_SOLVER_RESULTS_PROCESSED, \
            _METRIC_SOLVER_RESULTS_SYNCED, \
            _METRIC_SOLVER_RESULTS_SKIPPED, \
            _METRIC_SOLVER_RESULTS_FAILED = sync_solver_documents(document_ids, force_sync)

        if not only_one_kind or only_analysis_documents:
            _METRIC_ANALYSIS_RESULTS_PROCESSED, \
            _METRIC_ANALYSIS_RESULTS_SYNCED, \
            _METRIC_ANALYSIS_RESULTS_SKIPPED, \
            _METRIC_ANALYSIS_RESULTS_FAILED = sync_analysis_documents(document_ids, force_sync)

    if _THOTH_METRICS_PUSHGATEWAY_URL:
        try:
            _LOGGER.debug(
                f"Submitting metrics to Prometheus pushgateway {_THOTH_METRICS_PUSHGATEWAY_URL}")
            push_to_gateway(_THOTH_METRICS_PUSHGATEWAY_URL, job='graph-sync',
                            registry=prometheus_registry)
        except Exception as e:
            _LOGGER.exception(
                f'An error occurred pushing the metrics: {str(e)}')


if __name__ == '__main__':
    _LOGGER.info(f"graph-sync-job v{__version__} starting...")

    cli()
