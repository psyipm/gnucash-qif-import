#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
GnuCash Python helper script to import transactions from QIF text files into GnuCash's own file format.

https://github.com/hjacobs/gnucash-qif-import
'''

import argparse
import datetime
import json
import logging
import os
from mtp import *
import qif
from decimal import Decimal

from gnucash import Session, Transaction, Split, GncNumeric


def lookup_account_by_path(root, path):
    acc = root.lookup_by_name(path[0])
    if acc.get_instance() is None:
        raise Exception('Account path {} not found'.format(':'.join(path)))
    if len(path) > 1:
        return lookup_account_by_path(acc, path[1:])
    return acc


def lookup_account(root, name):
    path = name.split(':')
    return lookup_account_by_path(root, path)


def add_transaction(book, item, currency):
    logging.info(
        'Adding transaction for account "%s" (%s %s)..',
        item.account, item.split_amount, currency.get_mnemonic()
    )

    tx = Transaction(book)
    tx.BeginEdit()
    tx.SetCurrency(currency)
    tx.SetDateEnteredTS(datetime.datetime.now())
    tx.SetDatePostedTS(item.date)
    tx.SetDescription(item.memo)

    root = book.get_root_account()
    acc = lookup_account(root, item.account)
    add_split(book, acc, tx, to_gnc_numeric(item, currency))

    acc2 = lookup_account(root, item.split_category)
    add_split(book, acc2, tx, to_gnc_numeric(item, currency, -1))

    tx.CommitEdit()


def add_split(book, account, transaction, amount):
    split = Split(book)
    split.SetParent(transaction)
    split.SetAccount(account)
    split.SetValue(amount)
    split.SetAmount(amount)


def to_gnc_numeric(item, currency, positive=1):
    item_amount = Decimal(item.split_amount.replace(',', '.'))
    amount = int(item_amount * currency.get_fraction())

    return GncNumeric(amount * positive, currency.get_fraction())


def read_entries(fn, imported):
    logging.debug('Reading %s..', fn)
    if fn.startswith(MTP_SCHEME):
        items = read_entries_from_mtp(fn[len(MTP_SCHEME):], imported)
    else:
        base = os.path.basename(fn)
        if base in imported:
            logging.info('Skipping %s (already imported)', base)
            return []
        with open(fn) as fd:
            items = qif.parse_qif(fd)
        imported.add(fn)
    logging.debug('Read %s items from %s', len(items), fn)
    return items


def item_already_in_book(book, item, currency):
    '''Find transaction by description than check date and amount'''

    root = book.get_root_account()
    acc = lookup_account(root, item.account)

    transaction = acc.FindTransByDesc(item.memo)
    if not transaction:
        return False

    tx_date = datetime.datetime.fromtimestamp(transaction.GetDate())
    if tx_date.strftime('%Y-%m-%d') != item.date.strftime('%Y-%m-%d'):
        return False

    tx_amount = transaction.GetAccountAmount(acc)

    return tx_amount.equal(to_gnc_numeric(item, currency))


def write_transactions_to_gnucash(gnucash_file, currency, all_items, dry_run=False, date_from=None):
    logging.debug('Opening GnuCash file %s..', gnucash_file)

    session = Session(gnucash_file)
    book = session.book
    commod_tab = book.get_table()
    currency = commod_tab.lookup('ISO4217', currency)

    if date_from:
        date_from = datetime.datetime.strptime(date_from, '%Y-%m-%d')

    imported_items = set()
    for item in all_items:
        if date_from and item.date < date_from:
            logging.info('Skipping entry %s (%s)', item.date.strftime('%Y-%m-%d'), item.split_amount)
            continue
        if item_already_in_book(book, item, currency) or (item.as_tuple() in imported_items):
            logging.info('Skipping entry %s (%s) --- already imported!', item.date.strftime('%Y-%m-%d'),
                         item.split_amount)
            continue
        add_transaction(book, item, currency)
        imported_items.add(item.as_tuple())

    if dry_run:
        logging.debug('** DRY-RUN **')
    else:
        logging.debug('Saving GnuCash file..')
        session.save()
    session.end()


def main(args):
    if args.verbose:
        lvl = logging.DEBUG
    elif args.quiet:
        lvl = logging.WARN
    else:
        lvl = logging.INFO

    logging.basicConfig(level=lvl)

    imported_cache = os.path.expanduser('~/.gnucash-qif-import-cache.json')
    if os.path.exists(imported_cache):
        with open(imported_cache) as fd:
            imported = set(json.load(fd))
    else:
        imported = set()

    all_items = []
    for fn in args.file:
        all_items.extend(read_entries(fn, imported))

    if all_items:
        write_transactions_to_gnucash(args.gnucash_file, args.currency, all_items, dry_run=args.dry_run,
                                      date_from=args.date_from)

    if not args.dry_run:
        with open(imported_cache, 'wb') as fd:
            json.dump(list(imported), fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-v', '--verbose', help='Verbose (debug) logging', action='store_true')
    parser.add_argument('-q', '--quiet', help='Silent mode, only log warnings', action='store_true')
    parser.add_argument('--dry-run', help='Noop, do not write anything', action='store_true')
    parser.add_argument('--date-from', help='Only import transaction >= date (YYYY-MM-DD)')
    parser.add_argument('-c', '--currency', metavar='ISOCODE', help='Currency ISO code (default: EUR)', default='EUR')
    parser.add_argument('-f', '--gnucash-file', help='Gnucash data file')
    parser.add_argument('file', nargs='+',
                        help='Input QIF file(s), can also be "mtp:<PATTERN>" to import from MTP device')

    args = parser.parse_args()
    main(args)
