import tensorflow as tf
import numpy as np
from utils.vocab_utils import Vocab


class TextCNN(object):
    """
    A CNN for text classification.
    Uses an embedding layer, followed by a convolutional, max-pooling and softmax layer.
    """
    def __init__(
      self, sequence_length, num_classes, vocab_size,
      embedding_size, filter_sizes, num_filters, l2_reg_lambda=0.0, word_vocab=None, use_char=False, char_sequence_length=None):

        # Placeholders for input, output and dropout
        self.input_x = tf.placeholder(tf.int32, [None, sequence_length], name="input_x")
        self.input_x_char = tf.placeholder(tf.int32, [None, char_sequence_length], name="input_x_char")
        self.input_y = tf.placeholder(tf.float32, [None, num_classes], name="input_y")
        self.dropout_keep_prob = tf.placeholder(tf.float32, name="dropout_keep_prob")
        
        word_vec_trainable = True
        cur_device = '/gpu:0'
        # if fix_word_vec: 
        #     word_vec_trainable = False
        #     cur_device = '/cpu:0'


        # Keeping track of l2 regularization loss (optional)
        l2_loss = tf.constant(0.0)

        # Embedding layer
        with tf.device('/cpu:0'), tf.name_scope("embedding"):
            embedding_size = 100
            W = tf.Variable(
                tf.random_uniform([vocab_size, embedding_size], -1.0, 1.0),
                name="W")
            self.embedded_chars = tf.nn.embedding_lookup(W, self.input_x_char)
            self.embedded_chars_expanded = tf.expand_dims(self.embedded_chars, -1)
            with tf.device(cur_device):
                self.word_embedding = tf.get_variable("word_embedding", trainable=word_vec_trainable, 
                                                  initializer=tf.constant(word_vocab.word_vecs), dtype=tf.float32)
            self.embedded_words = tf.nn.embedding_lookup(self.word_embedding, self.input_x) # [batch_size, question_len, word_dim]
            self.embedded_words_expanded = tf.expand_dims(self.embedded_words, -1)
        num_filters_total = num_filters * len(filter_sizes)

        word_cnn = self.cnn(self.embedded_words_expanded, filter_sizes, embedding_size, num_filters, sequence_length, num_filters_total)
        if use_char:
            char_cnn = self.cnn(self.embedded_chars_expanded, filter_sizes, embedding_size, num_filters, char_sequence_length, num_filters_total)
            h_pool_flat = tf.concat([word_cnn, char_cnn], 1)
        else:
            h_pool_flat = word_cnn
        # Add dropout
        with tf.name_scope("dropout"):
            self.h_drop = tf.nn.dropout(h_pool_flat, self.dropout_keep_prob)

        # Final (unnormalized) scores and predictions
        with tf.name_scope("output"):
            W = tf.get_variable(
                "W",
                shape=[num_filters_total * 2 if use_char else num_filters_total, num_classes],
                initializer=tf.contrib.layers.xavier_initializer())
            b = tf.Variable(tf.constant(0.1, shape=[num_classes]), name="b")
            l2_loss += tf.nn.l2_loss(W)
            l2_loss += tf.nn.l2_loss(b)
            self.raw_scores = tf.nn.xw_plus_b(self.h_drop, W, b)
            self.scores = tf.nn.softmax(self.raw_scores, name="scores")
            self.predictions = tf.argmax(self.scores, 1, name="predictions")

        # CalculateMean cross-entropy loss
        with tf.name_scope("loss"):
#            losses = tf.nn.softmax_cross_entropy_with_logits(self.scores, self.input_y)
            losses = tf.nn.softmax_cross_entropy_with_logits(logits=self.raw_scores, labels=self.input_y)
            self.loss = tf.reduce_mean(losses) + l2_reg_lambda * l2_loss

        # Accuracy
        with tf.name_scope("accuracy"):
            correct_predictions = tf.equal(self.predictions, tf.argmax(self.input_y, 1))
            self.accuracy = tf.reduce_mean(tf.cast(correct_predictions, "float"), name="accuracy")

    def cnn(self, embeded, filter_sizes, embedding_size, num_filters, sequence_length, num_filters_total):
        # Create a convolution + maxpool layer for each filter size
        pooled_outputs = []
        for i, filter_size in enumerate(filter_sizes):
            with tf.name_scope("conv-maxpool-%s" % filter_size):
                # Convolution Layer
                filter_shape = [filter_size, embedding_size, 1, num_filters]
                W = tf.Variable(tf.truncated_normal(filter_shape, stddev=0.1), name="W")
                b = tf.Variable(tf.constant(0.1, shape=[num_filters]), name="b")
                conv = tf.nn.conv2d(
                    embeded,
                    W,
                    strides=[1, 1, 1, 1],
                    padding="VALID",
                    name="conv")
                # Apply nonlinearity
                h = tf.nn.relu(tf.nn.bias_add(conv, b), name="relu")
                # Maxpooling over the outputs
                pooled = tf.nn.max_pool(
                    h,
                    ksize=[1, sequence_length - filter_size + 1, 1, 1],
                    strides=[1, 1, 1, 1],
                    padding='VALID',
                    name="pool")
                pooled_outputs.append(pooled)
        # Combine all the pooled features
        h_pool = tf.concat(pooled_outputs, axis=3)
        h_pool_flat = tf.reshape(h_pool, [-1, num_filters_total])
        return h_pool_flat