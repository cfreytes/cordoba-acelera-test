#!/usr/bin/env python3
"""
Lee el Google Calendar público de la Agenda Multisectorial y guarda los
próximos eventos en agenda/eventos.json, que es lo que muestra la web.
Lo corre GitHub todos los días (ver .github/workflows/agenda.yml).
Si algo falla, no toca el archivo que ya existe.
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timedelta, timezone

CAL_ID = 'c_c16bbd7577ece12468dd84a69b324d123049a48d977bd671fc7a1dbae22a00be@group.calendar.google.com'
ICS_URL = 'https://calendar.google.com/calendar/ical/' + CAL_ID.replace('@', '%40') + '/public/basic.ics'
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'eventos.json')
CBA = timezone(timedelta(hours=-3))  # Córdoba no tiene horario de verano
# Categorías que usa la Agenda. Si el evento no trae una, se busca alguna de estas en su texto.
CATEGORIAS = ['Espectáculos', 'Deportivo', 'M.i.c.e', 'Académico', 'Tecnología', 'Institucional', 'Productivo', 'Científico']


def desescapar(t):
    return t.replace('\\n', '\n').replace('\\N', '\n').replace('\\,', ',').replace('\\;', ';').replace('\\\\', '\\').strip()


def leer_fecha(clave, valor):
    """Devuelve (fecha 'AAAA-MM-DD', hora 'HH:MM' o '')."""
    if 'VALUE=DATE' in clave or re.fullmatch(r'\d{8}', valor):
        return f'{valor[:4]}-{valor[4:6]}-{valor[6:8]}', ''
    dt = datetime.strptime(valor[:15], '%Y%m%dT%H%M%S')
    if valor.endswith('Z'):
        dt = dt.replace(tzinfo=timezone.utc).astimezone(CBA)
    return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M')


def categoria_de(ev):
    if ev.get('CATEGORIES'):
        return desescapar(ev['CATEGORIES']).split(',')[0].strip()
    texto = (ev.get('DESCRIPTION', '') + ' ' + ev.get('SUMMARY', '')).lower()
    m = re.search(r'categor[ií]a\s*:\s*([^\n\\]+)', texto)
    for c in CATEGORIAS:
        if (m and c.lower() in m.group(1)) or c.lower() in texto:
            return c
    return ''


def main():
    pedido = urllib.request.Request(ICS_URL, headers={'User-Agent': 'Mozilla/5.0 agenda-cordoba-acelera'})
    try:
        ics = urllib.request.urlopen(pedido, timeout=60).read().decode('utf-8')
    except Exception as e:
        print('No pude leer el calendario, dejo eventos.json como estaba:', e)
        return 0
    if 'BEGIN:VCALENDAR' not in ics:
        print('El calendario no es público o cambió de dirección. Dejo eventos.json como estaba.')
        return 0

    lineas = re.sub(r'\r?\n[ \t]', '', ics).splitlines()  # une las líneas partidas
    eventos, ev = [], None
    for l in lineas:
        if l == 'BEGIN:VEVENT':
            ev = {}
        elif l == 'END:VEVENT' and ev is not None:
            eventos.append(ev)
            ev = None
        elif ev is not None and ':' in l:
            clave, valor = l.split(':', 1)
            nombre = clave.split(';')[0]
            ev[nombre] = valor
            ev['_' + nombre] = clave

    hoy = datetime.now(CBA).strftime('%Y-%m-%d')
    a_revisar = []
    limite = (datetime.now(CBA) + timedelta(days=365)).strftime('%Y-%m-%d')
    salida = []
    for e in eventos:
        if 'DTSTART' not in e or e.get('STATUS') == 'CANCELLED':
            continue
        try:
            fecha, hora = leer_fecha(e['_DTSTART'], e['DTSTART'])
            fin, hora_fin = (leer_fecha(e['_DTEND'], e['DTEND']) if 'DTEND' in e else (fecha, ''))
        except ValueError:
            continue
        # Fechas mal cargadas en el calendario (por ejemplo, año 0206 en vez de 2026): no se publican
        if not ('2000' <= fecha[:4] <= '2100'):
            a_revisar.append({'fecha_cargada': fecha, 'titulo': desescapar(e.get('SUMMARY', '')), 'lugar': desescapar(e.get('LOCATION', ''))})
            continue
        if not hora and fin > fecha:  # en los eventos de día completo, la fecha de fin es el día siguiente
            fin = (datetime.strptime(fin, '%Y-%m-%d') - timedelta(days=1)).date().isoformat()
        if not ('2000' <= fin[:4] <= '2100') or fin < fecha:
            fin = fecha
        if fin < hoy or fecha > limite:
            continue
        desc = desescapar(e.get('DESCRIPTION', ''))
        link = e.get('URL', '') or (re.search(r'https?://[^\s<>"]+', desc) or [''])[0]
        item = {'fecha': fecha, 'titulo': desescapar(e.get('SUMMARY', 'Evento')),
                'categoria': categoria_de(e), 'lugar': desescapar(e.get('LOCATION', '')), 'link': link}
        if hora: item['hora'] = hora
        if hora_fin and hora_fin != hora: item['horaFin'] = hora_fin
        if fin != fecha: item['fin'] = fin
        salida.append(item)

    salida.sort(key=lambda x: (x['fecha'], x.get('hora', '')))
    if not salida:
        print('El calendario no tiene eventos próximos. Dejo eventos.json como estaba.')
        return 0
    with open(SALIDA, 'w', encoding='utf-8') as f:
        json.dump({'actualizado': datetime.now(CBA).isoformat(timespec='minutes'), 'eventos': salida, 'a_revisar': a_revisar}, f, ensure_ascii=False, indent=1)
    print(f'Listo: {len(salida)} eventos guardados en agenda/eventos.json')
    if a_revisar:
        print(f'Ojo: {len(a_revisar)} eventos tienen la fecha mal cargada en el Google Calendar y no se publicaron:')
        for r in a_revisar:
            print(f"  {r['fecha_cargada']}  {r['titulo']}  ({r['lugar']})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
