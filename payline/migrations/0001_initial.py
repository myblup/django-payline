# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion
import payline.models


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date', models.DateTimeField(help_text='When the transaction was made', null=True)),
                ('amount', models.DecimalField(max_digits=12, decimal_places=2)),
                ('transaction_id', models.CharField(verbose_name='Unique Payline identifier', max_length=50, editable=False, blank=True)),
                ('token', models.CharField(unique=True, max_length=36, verbose_name='Timestamped token used to identify the transaction')),
                ('result_code', models.CharField(max_length=8, verbose_name='Transaction success code', blank=True)),
                ('order_id', models.PositiveIntegerField(null=True)),
                ('order_type', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='contenttypes.ContentType', null=True)),
            ],
            options={
                'ordering': ('-date',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Wallet',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('wallet_id', models.CharField(default=payline.models.get_uuid4, unique=True, max_length=36, editable=False, db_index=True)),
                ('first_name', models.CharField(help_text='Card owner first name', max_length=30, verbose_name='First name')),
                ('last_name', models.CharField(help_text='Card owner last name', max_length=30, verbose_name='Last name')),
                ('card_number', models.CharField(max_length=20, verbose_name='Card number')),
                ('card_type', models.CharField(max_length=20, verbose_name='Card type', choices=[(b'CB', b'Carte Bleu / VISA / Mastercard'), (b'AMEX', b'American Express')])),
                ('card_expiry', models.CharField(help_text='Format: MMYY (eg 0213 for february 2013)', max_length=4, verbose_name='Card expiry')),
            ],
            options={
                'verbose_name': 'wallet',
                'verbose_name_plural': 'wallets',
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='transaction',
            name='wallet',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='payline.Wallet', help_text='Wallet holding payment information', null=True),
            preserve_default=True,
        ),
    ]
