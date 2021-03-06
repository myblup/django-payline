#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
from logging import getLogger
from os import path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import ugettext as _
from suds import WebFault
from suds.client import Client


logger = getLogger('payline')

#API_VERSION = "4.38" # version en cours (d'après les dates) quand les wsdl ont été intégrés au repo
API_VERSION = "4.60" # version courante (selon payline https://support.payline.com/hc/fr/articles/360000836848-Historique-de-version-de-l-API)


class PaylineProcessor(object):
    """Payline Payment Backend."""

    AUTHORIZE = 100
    AUTHORIZE_AND_VALIDATE = 101

    PAYMENT_SUCCESS = "00000"

    def __init__(self):
        """Instantiate suds client."""
        wsdl_dir = path.join(path.abspath(path.dirname(__file__)), 'wsdl/%s' % API_VERSION)

        payline_api = getattr(settings, 'PAYLINE_API', 'DirectPayment')
        if payline_api not in ('DirectPayment', 'WebPayment', 'MassPayment'):
            raise ValueError("Unsupported Payline API: %s" % payline_api)

        debug_mode = getattr(settings, 'PAYLINE_DEBUG', True)
        environment = 'homologation' if debug_mode else 'production'
        wsdl_path = path.join(wsdl_dir, environment,
                              "{0}API.wsdl".format(payline_api))
        wsdl_uri = 'file://%s' % wsdl_path

        merchant_id = getattr(settings, 'PAYLINE_MERCHANT_ID', '')
        api_key = getattr(settings, 'PAYLINE_KEY', '')
        self.vad_number = getattr(settings, 'PAYLINE_VADNBR', '')
        if api_key:
            if not merchant_id:
                raise ImproperlyConfigured('Missing: PAYLINE_MERCHANT_ID')
            if not self.vad_number:
                raise ImproperlyConfigured('Missing: PAYLINE_VADNBR')
        # Fallback to Euro if no currency code is defined in the settings.
        self.currency_code = getattr(settings, 'PAYLINE_CURRENCY_CODE', 978)
        self.client = Client(url=wsdl_uri,
                             username=merchant_id,
                             password=api_key)

    def validate_card(self, card_number, card_type, card_expiry, card_cvx):
        """Do an Authorization request to make sure the card is valid."""
        minimum_amount = 100  # 1€ is the smallest amount authorized
        payment = self.client.factory.create('ns1:payment')
        payment.amount = minimum_amount
        payment.currency = self.currency_code
        payment.action = self.AUTHORIZE
        payment.mode = 'CPT'  # CPT = comptant
        payment.contractNumber = self.vad_number
        order = self.client.factory.create('ns1:order')
        order.ref = str(uuid4())
        order.amount = minimum_amount
        order.currency = self.currency_code
        order.date = datetime.now().strftime("%d/%m/%Y %H:%M")
        card = self.client.factory.create('ns1:card')
        card.number = card_number
        card.type = card_type
        card.expirationDate = card_expiry
        card.cvx = card_cvx
        try:
            res = self.client.service.doAuthorization(payment=payment,
                                                      order=order,
                                                      card=card)
        except WebFault:
            logger.error("Payment backend failure", exc_info=True)
            return (False, None,
                    _("Payment backend failure, please try again later."))
        result = (res.result.code == self.PAYMENT_SUCCESS,
                  res.result.shortMessage + ': ' + res.result.longMessage)
        if result[0]:  # authorization was successful, now cancel it (clean up)
            self.client.service.doReset(transactionID=res.transaction.id,
                                        comment='Card validation cleanup')
        return result

    def create_update_wallet(self, wallet_id, last_name, first_name,
                             card_number, card_type, card_expiry, card_cvx,
                             create=True):
        """Create or update a customer wallet to hold payment information.

        Return True if the creation or update was successful.

        """
        wallet = self.client.factory.create('ns1:wallet')
        wallet.walletId = wallet_id
        wallet.lastName = last_name
        wallet.firstName = first_name
        wallet.card = self.client.factory.create('ns1:card')
        wallet.card.number = card_number
        wallet.card.type = card_type
        wallet.card.expirationDate = card_expiry
        wallet.card.cvx = card_cvx
        service = self.client.service.createWallet
        if not create:
            service = self.client.service.updateWallet
        try:
            res = service(contractNumber=self.vad_number, wallet=wallet)
        except:
            logger.error("Payment backend failure", exc_info=True)
            return (False,
                    _("Payment backend failure, please try again later."))
        return (res.result.code == "02500",  # success ?
                res.result.shortMessage + ': ' + res.result.longMessage)

    def get_wallet(self, wallet_id):
        """Get wallet information from Payline."""
        try:
            res = self.client.service.getWallet(
                contractNumber=self.vad_number,
                walletId=wallet_id)
        except WebFault:
            logger.error("Payment backend failure", exc_info=True)
            return (False,
                    _("Payment backend failure, please try again later."))
        return (res.result.code == "02500",  # success ?
                getattr(res, 'wallet', None),  # None is needed because of suds
                res.result.shortMessage + ': ' + res.result.longMessage)

    def make_wallet_payment(self, wallet_id, amount):
        """Make a payment from the given wallet."""
        amount_cents = amount * 100  # use the smallest unit possible (cents)
        payment = self.client.factory.create('ns1:payment')
        payment.amount = amount_cents
        payment.currency = self.currency_code
        payment.action = self.AUTHORIZE_AND_VALIDATE
        payment.mode = 'CPT'  # CPT = comptant
        payment.contractNumber = self.vad_number
        order = self.client.factory.create('ns1:order')
        order.ref = str(uuid4())
        order.amount = amount_cents
        order.currency = self.currency_code
        order.date = datetime.now().strftime("%d/%m/%Y %H:%M")
        try:
            res = self.client.service.doImmediateWalletPayment(
                payment=payment,
                order=order,
                walletId=wallet_id)
        except WebFault:
            logger.error("Payment backend failure", exc_info=True)
            return (False, None,
                    _("Payment backend failure, please try again later."))
        return (res.result.code == self.PAYMENT_SUCCESS,
                res.transaction.id,
                res.result.shortMessage + ': ' + res.result.longMessage)

    def make_web_payment(self, order_ref, amount, buyer=None):
        amount_cents = int(float(amount) * 100)

        # Payment information
        payment = self.client.factory.create('ns1:payment')
        payment.amount = amount_cents
        payment.currency = self.currency_code
        payment.action = self.AUTHORIZE_AND_VALIDATE
        payment.mode = 'CPT'
        payment.contractNumber = self.vad_number

        # Order information
        order = self.client.factory.create('ns1:order')
        order.ref = order_ref
        order.amount = amount_cents
        order.currency = self.currency_code
        order.date = datetime.now().strftime("%d/%m/%Y %H:%M")

        # Buyer information (if any)
        buyer_obj = buyer or {}
        buyer = self.client.factory.create('ns1:buyer')
        buyer.lastName = buyer_obj.get('first_name')
        buyer.firstName = buyer_obj.get('last_name')
        buyer.email = buyer_obj.get('email')
        #shipping_address = buyer_obj.get('shipping_address', {})
        #buyer.shippingAddress.name = shipping_address.get('name')
        #buyer.shippingAddress.street1
        #buyer.shippingAddress.street2
        #buyer.shippingAddress.cityName
        #buyer.shippingAddress.zipCode
        #buyer.shippingAddress.country
        #buyer.shippingAddress.phone
        #buyer.accountCreateDate
        #buyer.accountAverageAmount
        #buyer.accountOrderCount
        #buyer.walletId
        #buyer.walletDisplayed
        #buyer.walletSecured
        #buyer.walletCardInd
        buyer.ip = buyer_obj.get('ip')
        #buyer.mobilePhone = buyer_obj.get('mobile_phone')
        #buyer.customerId = buyer_obj.get('id')

        # URLs
        return_url = getattr(settings, 'PAYLINE_RETURN_URL', '')
        cancel_url = getattr(settings, 'PAYLINE_CANCEL_URL', '')
        notification_url = getattr(settings, 'PAYLINE_NOTIFICATION_URL', '')

        try:
            result = self.client.service.doWebPayment(
                payment=payment,
                buyer=buyer,
                returnURL=return_url,
                cancelURL=cancel_url,
                order=order,
                notificationURL=notification_url,
                selectedContractList=(self.vad_number, )
            )
        except WebFault:
            logger.error("Payment backend failure", exc_info=True)
            return (False, None)
        return (result.result.code == self.PAYMENT_SUCCESS, result)

    def get_web_payment_details(self, token):
        result = self.client.service.getWebPaymentDetails(
            # XXX Wot??? "version=3"  ???
            # XXX from the doc https://payline.atlassian.net/wiki/spaces/DT/pages/1052411285/Webservice+-+getWebPaymentDetailsRequest
            # version: Payline web services version. To be valued with the latest version: see the table of versions.
            # NB: atm, just switching this to v4 doesn't make much difference... I suspect this isn't even used
            # by their webservice :-/
            #version=3, 
            version=4, 
            token=token,
        )
        return (result.result.code == self.PAYMENT_SUCCESS, result)
