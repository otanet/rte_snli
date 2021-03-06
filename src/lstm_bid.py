#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import argparse
from datetime import datetime
import numpy as np
import pandas as pd

from keras.models import Sequential
from keras.layers import Dense, Embedding, Dropout, LSTM, TimeDistributed, Lambda
from keras.layers.normalization import BatchNormalization
from keras.layers.advanced_activations import PReLU
from keras.layers.wrappers import Bidirectional
from keras.layers import Merge
from keras.utils import np_utils
from keras import backend as K

from keras.callbacks import TensorBoard, EarlyStopping, ModelCheckpoint

from gensim.models import KeyedVectors

from src.util import load_data, load_embedding_index

np.random.seed(6162)

# =====arguments=====
parser = argparse.ArgumentParser()
parser.add_argument("--train_sampling", default=False, action="store_true", help="run sampled train data")
parser.add_argument("--embedding_dir", default="", help="path to GloVe embedding matrix")
parser.add_argument("--embedding_file", default="", help="GloVe file name")
parser.add_argument("--batch_size", type=int, default=512, help="batch size")
parser.add_argument("--nb_epochs", type=int, default=10, help="numbers of epochs to train for")
parser.add_argument("--lstm_dim", type=int, default=200, help="LSTM dim.")
parser.add_argument("--embedding_dim", type=int, default=200, help="embedding dim.")
parser.add_argument("--translation_dim", type=int, default=100, help="translation dim.")
parser.add_argument("--mlp_dim", type=int, default=300, help="mlp dim.")
parser.add_argument("--mlp_dropout", type=int, default=0.5, help="mlp dropout")
parser.add_argument("--model_dir", default="model/", help="path to model")
parser.add_argument("--tensorboard_dir", default="log/", help="path to save tensorboard logs")
arg = parser.parse_args()
print("Arguments: ", arg)

batch_size = arg.batch_size
nb_epochs = arg.nb_epochs
lstm_dim = arg.lstm_dim
embedding_dim = arg.embedding_dim
translation_dim = arg.translation_dim
mlp_dim = arg.mlp_dim
mlp_dropout = arg.mlp_dropout
tensorboard_log_dir = arg.tensorboard_dir

dt_str = datetime.now().strftime("%Y%m%d")
ut_str = datetime.now().strftime("%s")
exp_file_name = os.path.splitext(os.path.basename(__file__))[0]
exp_stamp = "{}.{}.{}_{}_{}_{}_{}_{}_{}".format(ut_str,
                                                exp_file_name,
                                                batch_size,
                                                nb_epochs,
                                                lstm_dim,
                                                embedding_dim,
                                                translation_dim,
                                                mlp_dim,
                                                mlp_dropout
                                                )

model_dir = os.path.join(arg.model_dir, dt_str)
if not os.path.isdir(model_dir):
    os.mkdir(model_dir)
model_name = os.path.join(model_dir, exp_stamp + ".model.json")
model_weights_name = os.path.join(model_dir, exp_stamp + ".weight.h5")
model_metrics_name = os.path.join(model_dir, exp_stamp + ".metrics.json")

tf_log_dir = os.path.join(tensorboard_log_dir, exp_stamp)
if not os.path.isdir(tf_log_dir):
    os.mkdir(tf_log_dir)

# =====data preprocess=====
X_train, y_train, X_dev, y_dev, X_test, y_test, tokenizer = load_data(train_sampling=arg.train_sampling)

# =====preapare embedding matrix=====
word_index = tokenizer.word_index
num_words = len(word_index)

embeddings_index = load_embedding_index(arg.embedding_dir, arg.embedding_file)

embedding_matrix = np.zeros((len(word_index) + 1, 200))
for word, i in word_index.items():
    embedding_vector = embeddings_index.get(word)
    if embedding_vector is not None:
        # words not found in embedding index will be all-zeros.
        embedding_matrix[i] = embedding_vector


# =====LSTM model=====
model1 = Sequential()
model1.add(Embedding(num_words + 1,
                     embedding_dim,
                     weights=[embedding_matrix],
                     trainable=False))
model1.add(Bidirectional(LSTM(lstm_dim, recurrent_dropout=0.5, dropout=0.5, return_sequences=True)))
model1.add(TimeDistributed(Dense(translation_dim, activation="relu")))
model1.add(Lambda(lambda x: K.sum(x, axis=1), output_shape=(100,)))

model2 = Sequential()
model2.add(Embedding(num_words + 1,
                     embedding_dim,
                     weights=[embedding_matrix],
                     trainable=False))
model2.add(Bidirectional(LSTM(lstm_dim, recurrent_dropout=0.5, dropout=0.5, return_sequences=True)))
model2.add(TimeDistributed(Dense(translation_dim, activation="relu")))
model2.add(Lambda(lambda x: K.sum(x, axis=1), output_shape=(100,)))

model = Sequential()
model.add(Merge([model1, model2], mode="concat"))
model.add(BatchNormalization())

model.add(Dense(mlp_dim))
model.add(PReLU())
model.add(Dropout(mlp_dropout))
model.add(BatchNormalization())

model.add(Dense(mlp_dim))
model.add(PReLU())
model.add(Dropout(mlp_dropout))
model.add(BatchNormalization())

model.add(Dense(mlp_dim))
model.add(PReLU())
model.add(Dropout(mlp_dropout))
model.add(BatchNormalization())

model.add(Dense(3, activation="sigmoid"))
model.compile(loss="categorical_crossentropy",
              optimizer="adam",
              metrics=["accuracy"]
              )

tensorboard = TensorBoard(log_dir=tf_log_dir)
history = model.fit(X_train, y_train,
                    batch_size=batch_size,
                    epochs=nb_epochs,
                    validation_data=(X_dev, y_dev),
                    shuffle=True,
                    callbacks=[tensorboard]
                    )

score, acc = model.evaluate(X_test, y_test, batch_size=batch_size)

print()
print("Test score:", score)
print("Test accuracy:", acc)

# =====save model and evaluation=====
model.save_weights(model_weights_name)
with open(model_name, "w") as f:
    f.write(model.to_json())

with open(model_metrics_name, "w") as f:
    json.dump(
        {
            "evaluation": {"test_score": score, "test_accuracy": acc},
            "parameter": vars(arg)
        },
        f)
