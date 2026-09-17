import base64
import csv
from datetime import date, timedelta
from io import BytesIO, StringIO
from xml.sax.saxutils import escape

import psycopg
from psycopg.rows import dict_row
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


COLUMNS = ('mode', 'executed_at', 'symbol', 'side', 'quantity', 'price', 'quote_currency', 'fee', 'fee_currency')


def export_report(dsn, user_id, start: date, end: date, format: str):
    if start > end or (end-start).days > 366:
        raise ValueError('Choose a date range of at most 367 days')
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        # UTC calendar dates and owner filters apply independently to both ledgers.
        rows = c.execute('''SELECT * FROM (
            SELECT 'paper' AS mode,t.created_at AS executed_at,t.symbol,t.side,t.quantity,t.price,
                'USD' AS quote_currency,t.fee,'USD' AS fee_currency
            FROM portfolio_trades t JOIN portfolios p USING(portfolio_id)
            WHERE p.user_id=%s AND t.created_at>=%s::date AT TIME ZONE 'UTC'
                AND t.created_at<%s::date AT TIME ZONE 'UTC'
            UNION ALL
            SELECT 'sandbox',f.executed_at,f.symbol,o.side,f.quantity,f.price,'USDT',f.fee,f.fee_currency
            FROM sandbox_fills f JOIN sandbox_orders o USING(order_id)
                JOIN trading_bots b ON b.bot_id=o.bot_id
            WHERE b.user_id=%s AND f.executed_at>=%s::date AT TIME ZONE 'UTC'
                AND f.executed_at<%s::date AT TIME ZONE 'UTC'
            ) trades ORDER BY executed_at,mode,symbol LIMIT 5001''',
            (user_id,start,end+timedelta(days=1),user_id,start,end+timedelta(days=1))).fetchall()
    return render_report(rows, start, end, format)


def render_report(rows, start, end, format):
    if len(rows) > 5000:
        raise ValueError('This range exceeds 5,000 fills. Choose a smaller range.')
    values = [[str(row[key]) for key in COLUMNS] for row in rows]
    if format == 'csv':
        stream = StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        # Neutralize spreadsheet formulas even if a provider supplies an unsafe symbol.
        writer.writerows([["'"+v if v.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else v for v in row] for row in values])
        raw, mime = stream.getvalue().encode('utf-8-sig'), 'text/csv'
    else:
        stream = BytesIO()
        styles = getSampleStyleSheet()
        small = styles['BodyText'].clone('small')
        small.fontSize, small.leading = 7, 9
        story = [Paragraph('Trading activity report', styles['Title']),
                 Paragraph(f'{start} through {end} (UTC) · {len(rows)} fills', styles['Normal']),
                 Paragraph('Paper USD and sandbox USDT are separate environments. Each sandbox row is an individual fill. Fees retain their recorded currency.', styles['Normal']), Spacer(1,12)]
        cells = [[Paragraph(escape(v.replace('_',' ')), small) for v in COLUMNS]]
        cells.extend([[Paragraph(escape(v),small) for v in row] for row in values])
        table = Table(cells, colWidths=[48,112,65,35,100,100,55,95,55], repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),0.3,colors.grey)]))
        story.append(table)
        SimpleDocTemplate(stream,pagesize=landscape(A4),leftMargin=24,rightMargin=24,topMargin=24,bottomMargin=24).build(story)
        raw,mime=stream.getvalue(),'application/pdf'
    return {'filename': f'trades-{start}-{end}.{format}', 'content_type': mime,
            'content_base64': base64.b64encode(raw).decode(), 'fill_count':len(rows)}
