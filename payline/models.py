#!/usr/bin/env python
# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from uuid import uuid4

from django.db import models
try:  # changed in Django 1.7
    from django.contrib.contenttypes.fields import GenericForeignKey
except ImportError:
    from django.contrib.contenttypes.generic import GenericForeignKey  # noqa
from django.contrib.contenttypes.models import ContentType

from django.utils.translation import ugettext_lazy as _

from .processor import PaylineProcessor


def get_uuid4():
    return str(uuid4())


def expiry_date_to_datetime(expiry_date):
    """Convert a credit card expiry date to a datetime object.

    The datetime is the last day of the month.

    """
    exp = datetime.strptime(expiry_date, '%m%y')  # format: MMYY
    # to find the next month
    # - add 31 days (more than a month) to the first day of the current month
    # - replace the day to be "1"
    # - substract one day
    exp += timedelta(days=31)
    exp = exp.replace(day=1)
    exp -= timedelta(days=1)
    return exp


class Wallet(models.Model):
    """Virtual Wallet: hold payment information."""
    CARD_TYPE_CHOICES = (
        ('CB', "Carte Bleu / VISA / Mastercard"),
        ('AMEX', "American Express"))
    wallet_id = models.CharField(
        max_length=36, default=get_uuid4,
        editable=False, db_index=True, unique=True)
    first_name = models.CharField(
        _("First name"), max_length=30, help_text=_("Card owner first name"))
    last_name = models.CharField(
        _("Last name"), max_length=30, help_text=_("Card owner last name"))
    card_number = models.CharField(_("Card number"), max_length=20)
    card_type = models.CharField(
        _("Card type"), max_length=20, choices=CARD_TYPE_CHOICES)
    card_expiry = models.CharField(
        _("Card expiry"), max_length=4,
        help_text=_("Format: MMYY (eg 0213 for february 2013)"))

    class Meta:
        verbose_name = _("wallet")
        verbose_name_plural = _("wallets")

    def __unicode__(self):
        return u"%s %s" % (self.first_name, self.last_name)

    def is_valid(self):
        """Return True if the card expiry date is in the future."""
        exp = expiry_date_to_datetime(self.card_expiry)
        today = datetime.today()
        return exp >= expiry_date_to_datetime(today.strftime('%m%y'))

    def expires_this_month(self):
        """Return True if the card expiry date is in this current month."""
        today = datetime.today().strftime("%m%y")
        return today == self.card_expiry

    def make_payment(self, amount):
        """Make a payment from this wallet."""
        pp = PaylineProcessor()
        result, transaction, message = pp.make_wallet_payment(self.wallet_id,
                                                              amount)
        if result:
            self.transaction_set.create(amount=amount,
                                        transaction_id=transaction)
        return (result, message)


class Transaction(models.Model):
    """Payment."""
    wallet = models.ForeignKey(
        Wallet, null=True, blank=True,
        on_delete=models.SET_NULL,  # do never ever delete
        help_text=_("Wallet holding payment information"))
    date = models.DateTimeField(help_text=_("When the transaction was made"),
                                null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_id = models.CharField(
        _("Unique Payline identifier"),
        max_length=50, editable=False, blank=True
    )
    token = models.CharField(
        _("Timestamped token used to identify the transaction"),
        max_length=36, unique=True,
    )
    result_code = models.CharField(
        _("Transaction success code"), max_length=8, blank=True
    )
    order_type = models.ForeignKey(ContentType, null=True,
                                   on_delete=models.SET_NULL)
    order_id = models.PositiveIntegerField(null=True)
    order_object = GenericForeignKey('order_type', 'order_id')

    def __unicode__(self):
        return "Transaction %s for order %s" % (
            self.transaction_id, self.order_id
        )

    class Meta:
        ordering = ('-date',)

    def validate(self, payment_details):
        self.result_code = payment_details.result.code
        self.date = datetime.strptime(payment_details.transaction.date,
                                      '%d/%m/%Y %H:%M')
        self.transaction_id = payment_details.transaction.id
        self.save()
