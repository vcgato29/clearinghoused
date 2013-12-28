#! /usr/bin/python3

"""Pay out dividends."""

import struct
import logging

from . import (util, config, exceptions, bitcoin, util)

FORMAT = '>QQ'
ID = 50
LENGTH = 8 + 8

def create (db, source, amount_per_share, asset, test=False):
    issuances = util.get_issuances(db, validity='Valid', asset=asset)
    total_shares = sum([issuance['amount'] for issuance in issuances])
    amount = amount_per_share * total_shares
    balances = util.get_balances(db, address=source, asset='XCP')
    if not balances or balances[0]['amount'] < amount:
        raise exceptions.BalanceError('Insufficient funds. (Check that the database is up‐to‐date.)')
    if not issuances:
        raise exceptions.DividendError('No such asset: {}.'.format(asset))
    # elif issuances[0]['divisible'] == True:
    #     raise exceptions.DividendError('Dividend‐yielding assets must be indivisible.')
    if not amount_per_share:
        raise exceptions.UselessError('Zero amount per share.')
    print('Total amount to be distributed in dividends:', amount / config.UNIT)
    asset_id = util.get_asset_id(asset)
    data = config.PREFIX + struct.pack(config.TXTYPE_FORMAT, ID)
    data += struct.pack(FORMAT, amount_per_share, asset_id)
    return bitcoin.transaction(source, None, None, config.MIN_FEE, data, test)

def parse (db, tx, message):
    dividend_parse_cursor = db.cursor()
    # Ask for forgiveness…
    validity = 'Valid'

    # Unpack message.
    try:
        amount_per_share, asset_id = struct.unpack(FORMAT, message)
        asset = util.get_asset_name(asset_id)
    except Exception:
        amount_per_share, asset = None, None
        validity = 'Invalid: could not unpack'

    if validity == 'Valid':
        if not amount_per_share:
            validity = 'Invalid: zero amount per share.'

    if validity == 'Valid':
        if asset in (0, 1):
            validity = 'Invalid: cannot send dividends to BTC or XCP'
        elif not util.valid_asset_name(asset):
            validity = 'Invalid: bad Asset ID'

    # Debit.
    if validity == 'Valid':
        issuances = util.get_issuances(db, validity='Valid', asset=asset)
        total_shares = sum([issuance['amount'] for issuance in issuances])
        amount = amount_per_share * total_shares
        validity = util.debit(db, tx['source'], 'XCP', amount)

    # Credit.
    if validity == 'Valid':
        balances = util.get_balances(db, asset=asset)
        for balance in balances:
            address, address_amount = balance['address'], balance['amount']
            util.credit(db, address, 'XCP', address_amount * amount_per_share)

    # Add parsed transaction to message‐type–specific table.
    dividend_parse_cursor.execute('''INSERT INTO dividends(
                        tx_index,
                        tx_hash,
                        block_index,
                        source,
                        asset,
                        amount_per_share,
                        validity) VALUES(?,?,?,?,?,?,?)''',
                        (tx['tx_index'],
                        tx['tx_hash'],
                        tx['block_index'],
                        tx['source'],
                        asset,
                        amount_per_share,
                        validity)
                  )
    if validity == 'Valid':
        logging.info('Dividend: {} paid {} per share of asset {} ({})'.format(tx['source'], amount_per_share / config.UNIT, asset, util.short(tx['tx_hash'])))

    dividend_parse_cursor.close()

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4