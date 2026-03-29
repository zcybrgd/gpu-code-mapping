sudo $(which ncu) --csv --set full --page source --print-source sass -o ncu_reports/6th_report ./matmul > metric_sass.csv

sudo $(which ncu) --csv --set full --warp-sampling-interval 0 --warp-sampling-max-passes 10 --page source --print-source sass -o ./ncu_reports/my_report_warp -f ./matmul > PC_sampling/corr_warp_tuned.csv

cuobjdump --dump-ptx ./matmul > matmul.ptx
cuobjdump --dump-sass --dump-ptx ./matmul > sass_ptx_mapping.txt
nvdisasm -g -sf ./matmul > sass_with_source.txt
