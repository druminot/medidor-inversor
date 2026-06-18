#!/bin/bash

upload_file() {
    local_file=$1
    remote_path=$2
    
    echo "Uploading $local_file to $remote_path"
    curl -s -u lautaro:lsistem19 "https://zoning-heat-groggy.ngrok-free.dev/cmd/?cmd=rm+-f+$remote_path" > /dev/null
    
    b64=$(base64 -i "$local_file" | tr -d '\n')
    chunk_size=4000
    len=${#b64}
    for (( i=0; i<len; i+=chunk_size )); do
        chunk="${b64:$i:$chunk_size}"
        curl -s -u lautaro:lsistem19 -G --data-urlencode "cmd=echo -n $chunk | base64 -d >> $remote_path" "https://zoning-heat-groggy.ngrok-free.dev/cmd/" > /dev/null
        echo -n "."
    done
    echo " Done."
}

upload_file "/Users/druminot/Documents/Codigos Varios/Medidor Inversor/Proyecto/inverter-simulator/simulator.py" "/opt/solar-monitor/inverter-simulator/simulator.py"
upload_file "/Users/druminot/Documents/Codigos Varios/Medidor Inversor/Proyecto/docker-compose.yml" "/opt/solar-monitor/docker-compose.yml"
upload_file "/Users/druminot/Documents/Codigos Varios/Medidor Inversor/Proyecto/sunvision-wine/Dockerfile" "/opt/solar-monitor/sunvision-wine/Dockerfile"
upload_file "/Users/druminot/Documents/Codigos Varios/Medidor Inversor/Proyecto/sunvision-wine/sv_cab/ConfigSunVision.xml" "/opt/solar-monitor/sunvision-wine/sv_cab/ConfigSunVision.xml"

echo "Restarting containers..."
curl -s -u lautaro:lsistem19 -G --data-urlencode "cmd=cd /opt/solar-monitor && docker compose build sunvision-wine inverter-simulator" "https://zoning-heat-groggy.ngrok-free.dev/cmd/"
curl -s -u lautaro:lsistem19 -G --data-urlencode "cmd=cd /opt/solar-monitor && docker compose up -d sunvision-wine inverter-simulator" "https://zoning-heat-groggy.ngrok-free.dev/cmd/"

