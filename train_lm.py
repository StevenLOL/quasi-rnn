from __future__ import print_function
import tensorflow as tf
from qrnn import QRNN_layer
import numpy as np
from model import QRNN_lm
from data_loader import ptb_batch_loader
import timeit
import json
import os


flags = tf.app.flags
flags.DEFINE_integer("epoch", 72, "Epochs to train (Def: 72).")
flags.DEFINE_integer("batch_size", 20, "Batch size (Def: 20).")
flags.DEFINE_integer("seq_len", 105, "Max sequences length. "
                                       " Specified at bucketizing (Def: 105).")
flags.DEFINE_integer("save_every", 2, "Batch frequency to save model and "
                                        "summary (Def: 100).")
flags.DEFINE_integer("qrnn_size", 640, "Number of qrnn units per layer "
                                       "(Def: 640).")
flags.DEFINE_integer("qrnn_layers", 2, "Number of qrnn layers (Def: 2). ")
flags.DEFINE_integer("qrnn_k", 2, "Width of QRNN filter (Def: 2). ")
flags.DEFINE_integer("emb_dim", 100, "Embedding dimension (Def: 100). ")
flags.DEFINE_integer("vocab_size", 10000, "Num words in vocab (Def: 10000). ")
flags.DEFINE_float("learning_rate", 1., "Beginning learning rate (Def: 1).")
flags.DEFINE_float("learning_rate_decay", 0.95, "After 6th epoch this "
                                                "factor is applied (Def: 0.95)")
flags.DEFINE_float("grad_clip", 10., "Clip norm value (Def: 10).")
flags.DEFINE_string("save_path", "lm-qrnn_model", "Save path "
                                                  "(Def: lm-qrnn_model).")
flags.DEFINE_string("data_dir", "data/ptb", "Data dir containing train/valid"
                                            "/test.txt files (Def: lm-qrnn_"
                                            "model).")
flags.DEFINE_boolean("do_train", True, "Flag for training (Def: True).")
flags.DEFINE_boolean("do_test", True, "Flag for testing (Def: True).")


FLAGS = flags.FLAGS

def main(_):
    args = FLAGS
    print('Parsed options: ')
    print(json.dumps(args.__flags, indent=2))

    if not os.path.exists(args.save_path):
        os.makedirs(args.save_path)

    bloader = ptb_batch_loader(args.data_dir, args.batch_size, args.seq_len)
    qrnn_lm = QRNN_lm(args)
    train(qrnn_lm, bloader, args)

def evaluate(sess, lm_model, loader, args, split='valid'):
    """ Evaluate an epoch over valid or test splits """
    val_loss = []
    batches_per_epoch = loader.batches_per_epoch[split]
    for batchX, batchY in loader.next_batch(split):
        fdict = {lm_model.words_in: batchX, lm_model.words_gtruth: batchY}
        loss = sess.run(lm_model.loss, feed_dict=fdict)
        val_loss.append(loss)
    m_val_loss = np.mean(val_loss)
    print("{} split mean loss: {}, perplexity: {}".format(split, m_val_loss,
                                                          np.exp(m_val_loss)))
    return m_val_loss

def train(lm_model, loader, args):
    def train_epoch(sess, epoch_idx, writer, merger, saver, save_path):
        """ Train a single epoch """
        tr_loss = []
        b_timings = []
        batches_per_epoch = loader.batches_per_epoch['train']
        batch_i = 0
        for batchX, batchY in loader.next_batch('train'):
            beg_t = timeit.default_timer()
            fdict = {lm_model.words_in: batchX, lm_model.words_gtruth:batchY}
            loss, _, summary = sess.run([lm_model.loss,
                                         lm_model.train_op,
                                         merger],
                                         feed_dict=fdict)
            tr_loss.append(loss)
            b_timings.append(timeit.default_timer() - beg_t)
            if batch_i % args.save_every == 0:
                writer.add_summary(summary, epoch_idx * batches_per_epoch + batch_i)
                checkpoint_file = os.path.join(save_path, 'model.ckpt')
                saver.save(sess, checkpoint_file,
                           global_step=epoch_idx * batches_per_epoch + batch_i)
                print("%4d/%4d (epoch %2d) tr_loss: %2.6f "
                      "mtime/batch: %2.6fs" % (batch_i, batches_per_epoch,
                                               epoch_idx, loss,
                                               np.mean(b_timings)))
            batch_i += 1
            if (batch_i + 1) >= batches_per_epoch:
                break
        return np.mean(tr_loss)
    with tf.Session() as sess:
        try:
            tf.global_variables_initializer().run()
            merged = tf.summary.merge_all()
        except AttributeError:
            # Backward compatibility
            tf.initialize_all_variables().run()
            merged = tf.merge_all_summaries()
        curr_lr = args.learning_rate
        saver = tf.train.Saver()
        train_writer = tf.train.SummaryWriter(os.path.join(args.save_path,
                                                           'train'),
                                              sess.graph)
        for epoch_idx in range(args.epoch):
            epoch_loss = train_epoch(sess, epoch_idx, train_writer,
                                     merged, saver, args.save_path)
            print('End of epoch {} with avg loss {} and '
                  'perplexity {}'.format(epoch_idx, 
                                         epoch_loss,
                                         np.exp(epoch_loss)))
            if epoch_idx >= 5:
                curr_lr = curr_lr * args.learning_rate_decay
                decay_op = lm_model.lr.assign(curr_lr)
                sess.run(decay_op)
            # reset states
            lm_model.reset_states(sess)
            val_loss = evaluate(sess, lm_model, loader, args)
            # reset states after evaluating
            lm_model.reset_states(sess)



if __name__ == '__main__':
    tf.app.run()
