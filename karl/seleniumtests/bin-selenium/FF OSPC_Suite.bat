' runs test1.html against FF
'saves results as results_fx_kdi-dev_OSPC_Suite.html

echo " runs test1.html against FF"
echo "saves results as results_fx_kdi-dev_OSPC_Suite.html"

java -jar "selenium-server-1.0.1\selenium-server.jar" -htmlSuite "*firefox" "http://kdi-dev.sixfeetup.com:8300/" "../all_suite1.html" "../log/results_fx_kdi-dev_OSPC_Suite.html"

