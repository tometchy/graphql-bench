#!/usr/bin/env python3

import yaml
import json

import subprocess

import argparse
import multiprocessing
from time import sleep

import sys
import os
import socket

from plot import run_dash_server

# ToDo: Make this configurable if 0 then skip printing
print("Sleeping 60 seconds to give time for services to load")
sleep(60)
print("Waiting time is over, starting benchmarking")

cpuCount = multiprocessing.cpu_count()
fileLoc = os.path.dirname(os.path.abspath(__file__))

def eprint(msg, indent):
    print((' ' * 2 * indent) + msg, file=sys.stderr)

def runWrk2(url, queriesFile, query, rps, openConns, duration, luaScript):

    luaScript = luaScript if luaScript else os.path.join(fileLoc, "bench.lua")

    p = subprocess.run(
        ["wrk2",
         "-R", str(rps),
         "-c", str(openConns),
         "-d", str(duration),
         "-t", str(cpuCount),
         "-L",
         "-s", luaScript,
         "--timeout", "1s",
         url,
         queriesFile,
         query
        ],
        env = dict(
            os.environ,
            LUA_PATH="/usr/share/lua/5.1/?.lua;" + os.path.join(fileLoc, "?.lua") + ';;',
            LUA_CPATH="/usr/lib/lua/5.1/?.so;/usr/lib/x86_64-linux-gnu/lua/5.1/?.so;;"
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding='utf-8'
    )

    if p.returncode != 0:
        for l in p.stderr.splitlines():
            eprint(l, 3)
        return None
    else:
        for l in p.stdout.splitlines():
            eprint(l, 3)
        return json.loads(p.stderr)

def benchCandidate(url, queriesFile, query, rpsList, openConns, duration, luaScript):
    results = {}
    for rps in rpsList:
        eprint("+" * 20, 3)
        eprint("{rps}Req/s Duration:{duration}s open connections:{openConns}".format(
            rps=rps,
            duration=duration,
            openConns=openConns
        ), 3)
        res = runWrk2(url, queriesFile, query, rps, openConns, duration, luaScript)
        results[rps] = res
    return results

def benchQuery(benchParams):

    benchName = benchParams["name"]

    eprint("=" * 20, 0)
    eprint("benchmark: {}".format(benchName), 0)

    rpsList = benchParams["rps"]
    timeout = benchParams.get("timeout", 1)
    duration = benchParams["duration"]
    openConns = benchParams.get("open_connections", 20)
    warmupDuration = benchParams.get("warmup_duration", None)
    query = benchParams.get("query")
    queriesFile = benchParams.get("queries_file")

    results = {}

    for candidate in benchParams["candidates"]:

        candidateName = candidate["name"]
        notResolvedUrl = candidate["url"]
        hostName = candidate["host_name"]
        print ("Not resolved url: {0}".format(notResolvedUrl))
        print ("Host name: {0}".format(hostName))
        resolvedHostIp = socket.gethostbyname(hostName)
        # Maybe there is method in socket or in other library to resolve name within url, google it before implementing our way
        print ("Resolved host ip: {0}".format(resolvedHostIp))
        candidateUrl = notResolvedUrl.replace(hostName, resolvedHostIp, 1)
        print ("Resolved url: {0}".format(candidateUrl ))
        candidateQuery = candidate.get("query", query)
        candidateQueriesFile = candidate.get("queries_file", queriesFile)
        candidateLuaScript = candidate.get('lua_script')

        eprint("-" * 20, 1)
        eprint("candidate: {} on {} at {}".format(candidateQuery, candidateName, candidateUrl), 1)

        if warmupDuration:
            eprint("Warmup:", 2)
            benchCandidate(candidateUrl, candidateQueriesFile, candidateQuery,
                           rpsList, openConns, warmupDuration, candidateLuaScript)

        eprint("Benchmark:", 2)
        candidateRes = benchCandidate(candidateUrl, candidateQueriesFile, candidateQuery,
                                      rpsList, openConns, duration, candidateLuaScript)
        results[candidateName] = candidateRes

    return {
        "benchmark": benchName,
        "results": results
    }

def bench(args):
    benchSpecs = yaml.load(args.spec)
    bench = args.bench
    if bench:
        benchSpecs = list(filter(lambda bs: bs['name'] == bench, benchSpecs))
        if not benchSpecs:
            print("no such benchmark exists in the spec: {}".format(query))
            sys.exit(1)
    results = []
    for benchSpec in benchSpecs:
        results.append(benchQuery(benchSpec))
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--spec', nargs='?', type=argparse.FileType('r'),
        default=sys.stdin)
    parser.add_argument('--bench', nargs='?', type=str)
    args = parser.parse_args()
    file = open("/graphql-bench/bench.yaml", "r") 
    args.spec = file.read()
    results = bench(args)
    run_dash_server(results)
