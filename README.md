# gpu-code-mapping
performance counters to PTX correlation framework

to our knowledge, there is no way to observe correlated stalls to code heatmaps except using the Nsight Compute GUI
which makes the automation process labour-intensive for an important set of benchmarks

this repo is to build an automated pipeline that provide for each profiled kernel, a heatmap that highlights source/PTX/SASS regions that suffers from stalls
