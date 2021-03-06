# pylint: disable=C0103,C0111,W0614

from __future__ import print_function

import ida_idaapi
from ida_hexrays import *
from collections import defaultdict

class CEmotetCFF(optblock_t):
    def __init__(self):
        optblock_t.__init__(self)
        self.isOptimize = False

    def FindDispatchReg(self, mba):
        infoCollectorObj = CDispatchFinder()
        mba.for_all_topinsns(infoCollectorObj)
        return infoCollectorObj.GetDispatchList()

    def FindBlockStatus(self, mba, dispatchReg):
        blockCnt = mba.qty
        statusResult = defaultdict()

        for i in range(1, blockCnt - 1):
            currentBlock = mba.get_mblock(i)
            if currentBlock.tail != None and currentBlock.tail.opcode in [m_jz, m_jnz]:
                mins = currentBlock.tail
                if mins.l.is_reg() and mins.r.is_constant():
                    if get_mreg_name(mins.l.r, mins.l.size) == dispatchReg:
                        status = mins.r.value(False)
                        if mins.opcode == m_jz:
                            #print("status 0x%X match with block %d" % (status, mins.d.b))
                            statusResult[status] = mins.d.b
                        elif mins.opcode == m_jnz:
                            #print("status 0x%X match with block %d" % (status, currentBlock.nextb.serial))
                            statusResult[status] = currentBlock.nextb.serial

        return statusResult

    def CorrectBlock(self, mba, dispatchReg, statusList):
        blockCnt = mba.qty
        changed = 0
        
        fixStatusList = []
        wontFixStatusList = []
        
        for i in range(1, blockCnt - 1):
            currentBlock = mba.get_mblock(i)
            
            #We find micro instruction mov dispatchReg, const
            mins = currentBlock.head
            while mins != currentBlock.tail:
            
                if mins == None:
                    break
                    
                if mins.opcode == m_mov and mins.l.t == mop_n and mins.d.is_reg():
                    if get_mreg_name(mins.d.r, mins.d.size) == dispatchReg:
                        #print(mins.dstr())
                        status = mins.l.value(False)
                        if status in statusList:
                        
                            if currentBlock.type != BLT_1WAY:
                                wontFixStatusList.append(status)
                                break

                            #Get block match with status
                            dstBlock = mba.get_mblock(statusList[status])
                            
                            #We delete mov dispatchReg, const instruction
                            currentBlock.make_nop(mins)
                            
                            #Check
                            if dstBlock.serial == currentBlock.serial:
                                break
                            
                            
                            #Insert/replace goto block
                            minsGoto = minsn_t(currentBlock.tail.ea)
                            if currentBlock.tail.opcode == m_goto:
                                currentBlock.tail.l._make_blkref(dstBlock.serial)
                            else:
                                minsGoto.opcode = m_goto
                                minsGoto.l._make_blkref(dstBlock.serial)
                                minsGoto.r = mop_t()
                                minsGoto.d = mop_t()
                                minsGoto.iprops = 0
                                currentBlock.insert_into_block(minsGoto, currentBlock.tail)

                            
                            
                            #Correct predset and succset
                            for oldDstBlockSerial in currentBlock.succset:
                                oldDstBlock = mba.get_mblock(oldDstBlockSerial)
                                oldDstBlock.predset._del(currentBlock.serial)
                            
                            for oldPresetSerial in dstBlock.predset:
                                oldPresetBlock = mba.get_mblock(oldPresetSerial)
                                

                            dstBlock.predset.push_back(currentBlock.serial)
                            
                            currentBlock.succset.clear()
                            currentBlock.succset.push_back(dstBlock.serial)
                            
                            mba.verify(True)
                            
                            if status not in wontFixStatusList:
                                if status not in fixStatusList:
                                    fixStatusList.append(status)
                            
                            #process next block
                            break
                
                #Update to handle control flow status set like this
                #v0 = result != 0 ? 61721445 : 200024545;
                    
                if mins.opcode == m_add and mins.l.t == mop_d and mins.r.t == mop_n and mins.d.t == mop_r and get_mreg_name(mins.d.r, mins.d.size) == dispatchReg:
                    subMins1 = mins.l.d
                    if subMins1.opcode == m_and and subMins1.l.t == mop_d and subMins1.r.t == mop_n:
                        subMins2 = subMins1.l.d
                        if subMins2.opcode == m_neg and subMins2.l.t == mop_d:
                            subMins3 = subMins2.l.d
                            if subMins3.opcode == m_xdu and subMins3.l.t == mop_d:
                                subMins4 = subMins3.l.d
                                if subMins4.opcode == m_setnz and subMins4.l.t == mop_r and subMins4.r.t == mop_n and subMins4.r.value(False) == 0:
                                    status1 = mins.r.value(False)
                                    status2 = (mins.r.value(False) + subMins1.r.value(False)) & 0xFFFFFFFF
                                    if status1 in statusList and status2 in statusList:
                                        #We need to do 2 thing: Fix current block from 1WAY to 2WAY and insert new block. This is an if/else stament
                                        
                                        #TODO: Fix the bug
                                        if currentBlock.tail.opcode == m_goto:
                                            currentBlock.make_nop(currentBlock.tail)
                                        
                                        for oldDstBlockSerial in currentBlock.succset:
                                            oldDstBlock = mba.get_mblock(oldDstBlockSerial)
                                            oldDstBlock.predset._del(currentBlock.serial)
                                        currentBlock.succset.clear()
                                        
                                        newDstBlockSerial = statusList[status2]
                                        if currentBlock.serial not in mba.get_mblock(newDstBlockSerial).predset:
                                            mba.get_mblock(newDstBlockSerial).predset.push_back(currentBlock.serial)
                                        
                                            
                                        insertedJnzIns = minsn_t(currentBlock.tail.ea)
                                        insertedJnzIns.opcode = m_jnz
                                        insertedJnzIns.l = mop_t()
                                        insertedJnzIns.l.make_reg(subMins4.l.r, 4)
                                        insertedJnzIns.r = mop_t()
                                        insertedJnzIns.r.make_number(subMins4.r.value(False), 4)
                                        insertedJnzIns.d = mop_t()
                                        insertedJnzIns.d.make_blkref(newDstBlockSerial)
                                        currentBlock.insert_into_block(insertedJnzIns, currentBlock.tail)
                                        
                                        #I don't know why currentBlock.type = BLT_2WAY throw exception so set it to BLT_NONE (not computed yet)
                                        currentBlock.type = BLT_NONE
                                        currentBlock.succset.push_back(newDstBlockSerial)
                                            
                                        #Because new block will be inserted before current block so we use currentBlock.serial + 1
                                        newInsertedBlock = mba.insert_block(currentBlock.serial + 1)

                                            
                                        #After insert new block, We should update block sertial in statusList
                                        #Old statuses in predset and succset were updated by insert_block even in current block so we don't have to care about it
                                        for s in statusList:
                                            if statusList[s] > currentBlock.serial:
                                                statusList[s] += 1
                                        
                                        currentBlock.succset.push_back(newInsertedBlock.serial)
                                        newInsertedBlock.predset.push_back(currentBlock.serial)
                                        newGotoBlockSerial = statusList[status1]
                                        mba.get_mblock(newGotoBlockSerial).predset.push_back(newInsertedBlock.serial)
                                        insertedGotoIns = minsn_t(currentBlock.tail.ea)
                                        insertedGotoIns.opcode = m_goto
                                        insertedGotoIns.l._make_blkref(newGotoBlockSerial)
                                        insertedGotoIns.r = mop_t()
                                        insertedGotoIns.d = mop_t()
                                        newInsertedBlock.insert_into_block(insertedGotoIns, None)

                                            
                                        newInsertedBlock.succset.push_back(newGotoBlockSerial)
                                        newInsertedBlock.type = BLT_NONE
                                        newInsertedBlock.start = currentBlock.start
                                        newInsertedBlock.end = currentBlock.end
                                        newInsertedBlock.flags = currentBlock.flags
                                        newInsertedBlock.mark_lists_dirty()
                                        
                                        currentBlock.make_nop(mins)
                                        currentBlock.mark_lists_dirty()
                                        
                                        mba.verify(True)
                                        
                                        fixStatusList.append(status1)
                                        fixStatusList.append(status2)
                                            
                                        break
                
                mins = mins.next
        
        #Process final fixStatusList to return
        fixStatusList = list(dict.fromkeys(fixStatusList))
        wontFixStatusList = list(dict.fromkeys(wontFixStatusList))
        finalFixStatusList = [x for x in fixStatusList if x not in wontFixStatusList]
        return finalFixStatusList

    def CleanDispatch(self, mba, dispatchReg, fixStatusList):
        dispatchCleanerObj = CDispatchCleaner()
        dispatchCleanerObj.SetDispatchReg(dispatchReg)
        dispatchCleanerObj.SetFixStatusList(fixStatusList)
        mba.for_all_topinsns(dispatchCleanerObj)
        return dispatchCleanerObj.changed

    def func(self, blk):
        mba = blk.mba

        if mba.maturity != MMAT_GLBOPT1:
            self.isOptimize = False
            return 0

        if self.isOptimize == True:
            return 0

        self.isOptimize = True

        changed = 0
        dispatchDict = self.FindDispatchReg(mba)
        for k, v in dispatchDict.items():
            if v >= 3: #If reg was compare with const at least 3 times, consider it's dispatch reg
                blockStatus = self.FindBlockStatus(mba, k)
                fixStatusList = self.CorrectBlock(mba, k, blockStatus)
                changed += len(fixStatusList)
                changed += self.CleanDispatch(mba, k, fixStatusList)

        #Perform optimize
        mba.mark_chains_dirty()
        mba.optimize_local(0)
        mba.verify(True)

        return changed

class CDispatchFinder(minsn_visitor_t):
    def __init__(self):
        minsn_visitor_t.__init__(self)
        self.dispatchResult = defaultdict()

    def visit_minsn(self):
        #Collect info about mov var, const and jnz/jz var, dst
        ins = self.curins
        if ins.opcode in [m_jz, m_jnz]:
            if ins.r.t == mop_n and ins.l.t == mop_r:
                regName = get_mreg_name(ins.l.r, ins.l.size)
                if regName in self.dispatchResult:
                    self.dispatchResult[regName] += 1
                else:
                    self.dispatchResult[regName] = 1

        return 0

    def GetDispatchList(self):
        return self.dispatchResult

class CDispatchCleaner(minsn_visitor_t):
    def __init__(self):
        minsn_visitor_t.__init__(self)
        self.changed = 0
        self.fixStatusList = None
        self.dispatchReg = ""

    def SetFixStatusList(self, fixStatusList):
        self.fixStatusList = fixStatusList

    def SetDispatchReg(self, dispatchReg):
        self.dispatchReg = dispatchReg

    def visit_minsn(self):
        #Detect jnz/jz var, dst then NOP it
        ins = self.curins
        currentBlock = self.blk
        if ins.opcode in [m_jz, m_jnz]:
            if ins.r.t == mop_n and ins.l.t == mop_r:
                if self.dispatchReg == get_mreg_name(ins.l.r, ins.l.size) and ins.r.value(False) in self.fixStatusList:
                    #Now we clean block
                    jmpDst = ins.d.b
                    if ins.opcode == m_jz:
                        #print("clean " + ins.dstr())
                        self.blk.make_nop(ins)
                        dstBlock = self.mba.get_mblock(jmpDst)
                        dstBlock.predset._del(self.blk.serial)
                        self.blk.succset._del(jmpDst)
                        self.blk.type = BLT_1WAY
                    else: #m_jnz
                        #print("clean " + ins.dstr())
                        self.curins.opcode = m_goto
                        self.curins.l = mop_t()
                        self.curins.l._make_blkref(jmpDst)
                        self.curins.r = mop_t()
                        self.curins.d = mop_t()
                        self.blk.mark_lists_dirty()
                        for serial in self.blk.succset:
                            oldDstBlock = self.mba.get_mblock(serial)
                            if oldDstBlock.serial != jmpDst:
                                oldDstBlock.predset._del(self.blk.serial)

                        self.blk.succset.clear()
                        self.blk.succset.push_back(jmpDst)
                        self.blk.type = BLT_1WAY

                    self.mba.optimize_local(0)
                    self.mba.verify(True)
                    self.changed += 1
        return 0

class CEmotetDeobfuscator(ida_idaapi.plugin_t):
    flags = 0
    comment = "Emotet Deobfuscator (POC)"
    help = ""
    wanted_name = "Emotet Deobfuscator (POC)"
    wanted_hotkey = ""

    def __init__(self):
        self.actived = False
        self.emotetUnCFFObj = CEmotetCFF()
        return

    def init(self):
        print("Emotet Deobfuscator loaded")
        return ida_idaapi.PLUGIN_OK

    def run(self, arg):
        if self.actived == True:
            self.actived = False
            self.emotetUnCFFObj.remove()
            print("Emotet Deobfuscator de-actived")
        else:
            self.actived = True
            self.emotetUnCFFObj.install()
            print("Emotet Deobfuscator actived")

        return True

    def term(self):
        return

def PLUGIN_ENTRY():
    return CEmotetDeobfuscator()
